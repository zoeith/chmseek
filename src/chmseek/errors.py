from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChmseekError(Exception):
    code: str
    message: str
    hints: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "hints": self.hints,
            },
        }


def file_not_found(path: object) -> ChmseekError:
    return ChmseekError(
        "FILE_NOT_FOUND",
        f"File does not exist: {path}",
        ["Check the path and try again."],
    )
