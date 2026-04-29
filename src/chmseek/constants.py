from __future__ import annotations

APP_NAME = "chmseek"
SCHEMA_VERSION = 1
CHUNKER_VERSION = "section-aware-v1"

DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DEFAULT_EMBEDDING_DIM = 768
SUPPORTED_EMBEDDING_DIMS = {256, 512, 768}

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
NORMALIZE_EMBEDDINGS = True

ALLOWED_CONTENT_EXTENSIONS = {".htm", ".html", ".xhtml", ".txt"}
TOC_EXTENSIONS = {".hhc", ".hhk"}
ALLOWED_EXTRACTED_EXTENSIONS = ALLOWED_CONTENT_EXTENSIONS | TOC_EXTENSIONS

BLOCKED_EXTRACTED_EXTENSIONS = {
    ".bat",
    ".cab",
    ".cmd",
    ".css",
    ".dll",
    ".exe",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".lnk",
    ".msi",
    ".ocx",
    ".png",
    ".ps1",
    ".scr",
    ".svg",
    ".vbs",
    ".webp",
}

UNSAFE_HTML_TAGS = {"script", "style", "object", "embed", "iframe", "frame"}
