from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from chmseek.embeddings import resolve_device
from chmseek.errors import ChmseekError


class FakeDevice:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available


def install_fake_torch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cuda: bool = False,
    xpu: bool = False,
    mps: bool = False,
) -> None:
    fake_torch = SimpleNamespace(
        cuda=FakeDevice(cuda),
        xpu=FakeDevice(xpu),
        backends=SimpleNamespace(mps=FakeDevice(mps)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)


def test_resolve_device_accepts_xpu(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_torch(monkeypatch, xpu=True)

    assert resolve_device("xpu") == ("xpu", "xpu")


def test_resolve_device_fails_when_xpu_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_torch(monkeypatch, xpu=False)

    with pytest.raises(ChmseekError) as excinfo:
        resolve_device("xpu")

    assert excinfo.value.code == "XPU_UNAVAILABLE"


def test_resolve_device_treats_xpu_probe_error_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_probe_error() -> bool:
        raise RuntimeError("xpu probe failed")

    fake_torch = SimpleNamespace(
        cuda=FakeDevice(False),
        xpu=SimpleNamespace(is_available=raise_probe_error),
        backends=SimpleNamespace(mps=FakeDevice(False)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    with pytest.raises(ChmseekError) as excinfo:
        resolve_device("xpu")

    assert excinfo.value.code == "XPU_UNAVAILABLE"


@pytest.mark.parametrize(
    ("cuda", "xpu", "mps", "expected"),
    [
        (True, True, True, ("cuda", "cuda")),
        (False, True, True, ("xpu", "xpu")),
        (False, False, True, ("mps", "mps")),
        (False, False, False, ("cpu", "cpu")),
    ],
)
def test_resolve_device_auto_priority(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cuda: bool,
    xpu: bool,
    mps: bool,
    expected: tuple[str, str],
) -> None:
    install_fake_torch(monkeypatch, cuda=cuda, xpu=xpu, mps=mps)

    assert resolve_device("auto") == expected
