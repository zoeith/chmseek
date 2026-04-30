from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .constants import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MODEL,
    DEFAULT_MODEL_REVISION,
    DOCUMENT_PREFIX,
    NORMALIZE_EMBEDDINGS,
    QUERY_PREFIX,
)
from .errors import ChmseekError
from .utils import word_tokens


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = DEFAULT_MODEL
    dimension: int = DEFAULT_EMBEDDING_DIM
    allow_model_download: bool = False
    allow_remote_model_code: bool = False
    offline: bool = False
    model_revision: str | None = None
    device: str = "auto"


class EmbeddingBackend(Protocol):
    model_name: str
    dimension: int
    document_prefix: str
    query_prefix: str
    normalized: bool
    used_local_files_only: bool
    remote_model_code_allowed: bool
    model_revision: str | None
    requested_device: str
    resolved_device: str

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        ...

    def embed_query(self, text: str) -> np.ndarray:
        ...


def default_model_name() -> str:
    if os.environ.get("CHMSEEK_EMBEDDING_BACKEND", "").lower() == "fake":
        return "fake"
    return DEFAULT_MODEL


def make_embedding_backend(config: EmbeddingConfig) -> EmbeddingBackend:
    config = normalize_embedding_config(config)
    if config.dimension <= 0:
        raise ChmseekError("INVALID_EMBEDDING_DIM", "Embedding dimension must be positive.")
    if config.model_name == "fake":
        return FakeEmbeddingBackend(config.dimension, requested_device=config.device)
    return SentenceTransformersEmbeddingBackend(config)


def normalize_embedding_config(config: EmbeddingConfig) -> EmbeddingConfig:
    if config.model_name == DEFAULT_MODEL and config.model_revision is None:
        return EmbeddingConfig(
            model_name=config.model_name,
            dimension=config.dimension,
            allow_model_download=config.allow_model_download,
            allow_remote_model_code=config.allow_remote_model_code,
            offline=config.offline,
            model_revision=DEFAULT_MODEL_REVISION,
            device=config.device,
        )
    return config


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class FakeEmbeddingBackend:
    """Deterministic local embedding backend for tests and fixture demos."""

    model_name = "fake"
    document_prefix = DOCUMENT_PREFIX
    query_prefix = QUERY_PREFIX
    normalized = NORMALIZE_EMBEDDINGS
    used_local_files_only = True
    remote_model_code_allowed = False
    model_revision = None
    resolved_device = "cpu"

    def __init__(
        self, dimension: int = DEFAULT_EMBEDDING_DIM, requested_device: str = "auto"
    ) -> None:
        self.dimension = dimension
        self.requested_device = requested_device
        self.last_document_inputs: list[str] = []
        self.last_query_input: str | None = None

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        prefixed = [self.document_prefix + text for text in texts]
        self.last_document_inputs = prefixed
        return self._embed_prefixed(prefixed)

    def embed_query(self, text: str) -> np.ndarray:
        prefixed = self.query_prefix + text
        self.last_query_input = prefixed
        return self._embed_prefixed([prefixed])[0]

    def _embed_prefixed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _semantic_tokens(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                raw = int.from_bytes(digest, "big")
                index = raw % self.dimension
                sign = 1.0 if (raw >> 8) % 2 == 0 else -1.0
                vectors[row, index] += sign
        return normalize_matrix(vectors)


class SentenceTransformersEmbeddingBackend:
    document_prefix = DOCUMENT_PREFIX
    query_prefix = QUERY_PREFIX
    normalized = NORMALIZE_EMBEDDINGS

    def __init__(self, config: EmbeddingConfig) -> None:
        self.model_name = config.model_name
        self.dimension = config.dimension
        self.model_revision = config.model_revision
        self.remote_model_code_allowed = config.allow_remote_model_code
        self.requested_device = config.device
        model_device, resolved_device = resolve_device(config.device)
        self.resolved_device = resolved_device
        if config.allow_remote_model_code and not config.model_revision:
            raise ChmseekError(
                "REMOTE_MODEL_CODE_UNPINNED",
                "Remote model code was allowed without a pinned model revision.",
                [
                    "Pass --model-revision with an immutable commit SHA "
                    "or disable remote model code."
                ],
            )

        cached = is_model_cached(config.model_name)
        self.used_local_files_only = config.offline or not config.allow_model_download
        if config.offline and not cached:
            raise ChmseekError(
                "MODEL_NOT_CACHED_OFFLINE",
                f"Embedding model is not cached locally: {config.model_name}",
                ["Run once without --offline and with --allow-model-download."],
            )
        if not cached and not config.allow_model_download:
            raise ChmseekError(
                "MODEL_DOWNLOAD_REQUIRED",
                f"Embedding model is not cached locally: {config.model_name}",
                ["Pass --allow-model-download to permit the one-time model download."],
            )

        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - depends on optional runtime import state
            raise ChmseekError(
                "EMBEDDING_BACKEND_UNAVAILABLE",
                "sentence-transformers could not be imported.",
                ["Install dependencies with the Conda environment or requirements lockfile."],
            ) from exc

        local_files_only = config.offline or not config.allow_model_download
        kwargs = {
            "trust_remote_code": config.allow_remote_model_code,
            "revision": config.model_revision,
            "local_files_only": local_files_only,
            "device": model_device,
        }
        try:
            self._model = SentenceTransformer(config.model_name, **kwargs)
        except TypeError:
            kwargs.pop("local_files_only", None)
            try:
                self._model = SentenceTransformer(config.model_name, **kwargs)
            except Exception as exc:  # pragma: no cover
                raise self._load_error(exc) from exc
        except Exception as exc:  # pragma: no cover
            raise self._load_error(exc) from exc

    def _load_error(self, exc: Exception) -> ChmseekError:
        message = str(exc)
        if "trust_remote_code" in message or "remote code" in message.lower():
            return ChmseekError(
                "REMOTE_MODEL_CODE_REQUIRED",
                "The selected model appears to require remote model code.",
                [
                    "Prefer a model loading path that does not require remote code.",
                    "If you accept the risk, pass --allow-remote-model-code and --model-revision.",
                ],
            )
        return ChmseekError(
            "EMBEDDING_MODEL_LOAD_FAILED",
            f"Could not load embedding model {self.model_name}: {message}",
            ["Check offline/download flags and model cache state."],
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(
            [self.document_prefix + text for text in texts],
            show_progress_bar=True,
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([self.query_prefix + text], show_progress_bar=False)[0]

    def _encode(self, texts: list[str], *, show_progress_bar: bool) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=show_progress_bar,
        ).astype(np.float32)
        if vectors.shape[1] < self.dimension:
            raise ChmseekError(
                "EMBEDDING_DIM_TOO_LARGE",
                f"Model returned {vectors.shape[1]} dimensions, requested {self.dimension}.",
                ["Choose an embedding dimension supported by the model."],
            )
        if vectors.shape[1] > self.dimension:
            vectors = vectors[:, : self.dimension]
            vectors = normalize_matrix(vectors)
        return vectors.astype(np.float32)


def _semantic_tokens(text: str) -> list[str]:
    synonyms = {
        "configure": "configure",
        "configuration": "configure",
        "configuring": "configure",
        "setup": "configure",
        "set": "configure",
        "prepare": "configure",
        "project": "project",
        "analysis": "analysis",
        "analyze": "analysis",
        "running": "run",
        "run": "run",
        "workflow": "workflow",
        "tutorial": "workflow",
        "create": "create",
        "createsession": "createsession",
        "session": "session",
        "closesession": "closesession",
        "hresult": "hresult",
        "setparameter": "setparameter",
        "parameter": "parameter",
        "error": "error",
    }
    tokens: list[str] = []
    for token in word_tokens(text.lower()):
        if token in {"search_document:", "search_query:", "search_document", "search_query"}:
            continue
        tokens.append(synonyms.get(token, token))
    return tokens


def is_model_cached(model_name: str) -> bool:
    if model_name == "fake":
        return True
    env_paths = [
        os.environ.get("SENTENCE_TRANSFORMERS_HOME"),
        os.environ.get("HF_HOME"),
    ]
    cache_roots = [Path(value).expanduser() for value in env_paths if value]
    cache_roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    safe_name = "models--" + model_name.replace("/", "--")
    return any((root / safe_name).exists() for root in cache_roots)


def resolve_device(requested_device: str) -> tuple[object, str]:
    requested = (requested_device or "auto").lower()
    valid = {"auto", "cpu", "cuda", "mps", "directml"}
    if requested not in valid:
        raise ChmseekError(
            "INVALID_EMBEDDING_DEVICE",
            f"Unsupported embedding device: {requested_device}",
            ["Choose one of: auto, cpu, cuda, mps, directml."],
        )
    if requested == "cpu":
        return "cpu", "cpu"
    if requested == "directml":
        try:
            import torch_directml
        except Exception as exc:
            raise ChmseekError(
                "DIRECTML_UNAVAILABLE",
                "DirectML was requested but torch-directml is not installed.",
                ["Install torch-directml separately or use --device auto/cpu/cuda/mps."],
            ) from exc
        return torch_directml.device(), "directml"

    try:
        import torch
    except Exception as exc:
        if requested == "auto":
            return "cpu", "cpu"
        raise ChmseekError(
            "TORCH_UNAVAILABLE",
            f"{requested} was requested but torch could not be imported.",
            ["Install the embedding dependencies or use --device cpu."],
        ) from exc

    if requested == "cuda":
        if torch.cuda.is_available():
            return "cuda", "cuda"
        raise ChmseekError(
            "CUDA_UNAVAILABLE",
            "CUDA was requested but is not available to PyTorch.",
            ["Use --device auto or --device cpu, or install a CUDA-enabled PyTorch build."],
        )
    if requested == "mps":
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps", "mps"
        raise ChmseekError(
            "MPS_UNAVAILABLE",
            "MPS was requested but is not available to PyTorch.",
            ["Use --device auto or --device cpu."],
        )
    if torch.cuda.is_available():
        return "cuda", "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", "mps"
    return "cpu", "cpu"
