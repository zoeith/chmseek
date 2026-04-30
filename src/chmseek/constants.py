from __future__ import annotations

APP_NAME = "chmseek"
SCHEMA_VERSION = 2
CHUNKER_VERSION = "section-aware-v1"

DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DEFAULT_MODEL_REVISION = "e9b6763023c676ca8431644204f50c2b100d9aab"
DEFAULT_EMBEDDING_DIM = 768
SUPPORTED_EMBEDDING_DIMS = {256, 512, 768}

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
NORMALIZE_EMBEDDINGS = True

ALLOWED_CONTENT_EXTENSIONS = {".htm", ".html", ".xhtml", ".txt"}
TOC_EXTENSIONS = {".hhc", ".hhk"}
IMAGE_ASSET_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
ALLOWED_EXTRACTED_EXTENSIONS = ALLOWED_CONTENT_EXTENSIONS | TOC_EXTENSIONS | IMAGE_ASSET_EXTENSIONS

BLOCKED_EXTRACTED_EXTENSIONS = {
    ".bat",
    ".cab",
    ".cmd",
    ".css",
    ".dll",
    ".exe",
    ".ico",
    ".js",
    ".lnk",
    ".msi",
    ".ocx",
    ".ps1",
    ".scr",
    ".svg",
    ".vbs",
}

UNSAFE_HTML_TAGS = {"script", "style", "object", "embed", "iframe", "frame"}
