"""Embedding model interface, lazy singleton, and backfill helper.

Owns all ML behind the ``EmbeddingModel`` protocol so the rest of the
codebase stays free of fastembed / ONNX imports.  The fastembed optional
dependency group must be installed for real embeddings::

    pip install brain_ds[embeddings]

When fastembed is absent, ``get_default_model()`` returns ``None`` and
every embedding call is a no-op (graceful degradation).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from brain_ds.store.models import NodeRow

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try importing fastembed — wrapped so ImportError is silent.
# ---------------------------------------------------------------------------
try:
    from fastembed import TextEmbedding as _TextEmbedding  # type: ignore[import-untyped]

    _FASTEMBED_AVAILABLE = True
except ImportError:
    _TextEmbedding = None  # type: ignore[assignment,misc]
    _FASTEMBED_AVAILABLE = False


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbeddingModel(Protocol):
    """Minimal interface for embedding models used by this project."""

    @property
    def name(self) -> str:
        """Model identifier stored in the ``embeddings.model`` column."""
        ...

    def embed(self, text: str) -> list[float]:
        """Embed *text* and return a float vector."""
        ...


# ---------------------------------------------------------------------------
# fastembed implementation
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class FastEmbedModel:
    """Wraps ``fastembed.TextEmbedding`` as an ``EmbeddingModel``."""

    def __init__(self, model_name: str = _DEFAULT_MODEL_NAME) -> None:
        if not _FASTEMBED_AVAILABLE or _TextEmbedding is None:
            raise ImportError("fastembed is not installed — install brain_ds[embeddings]")
        self._model = _TextEmbedding(model_name=model_name)
        self._name = model_name

    @property
    def name(self) -> str:
        return self._name

    def embed(self, text: str) -> list[float]:
        # fastembed returns a generator of numpy arrays, one per document.
        result = list(self._model.embed([text]))
        return [float(v) for v in result[0]]


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_INSTANCE: EmbeddingModel | None = None


def _build_model() -> EmbeddingModel | None:
    """Construct and return a new ``FastEmbedModel``, or ``None`` when unavailable."""
    if not _FASTEMBED_AVAILABLE:
        return None
    try:
        return FastEmbedModel()
    except Exception:
        log.debug("FastEmbedModel construction failed; embedding disabled", exc_info=True)
        return None


def get_default_model() -> EmbeddingModel | None:
    """Return the process-wide singleton ``EmbeddingModel``, or ``None``.

    The model is constructed on the first call and re-used for the lifetime
    of the process.  Returns ``None`` when fastembed is not installed.
    """
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = _build_model()
    return _INSTANCE


# ---------------------------------------------------------------------------
# Node text assembly (shared source of truth with similarity.node_text_tokens)
# ---------------------------------------------------------------------------

_SECTION_CONTENT_CAP = 400
_LOW_SIGNAL = frozenset({"ok", "n/a", "na", "none", "unknown"})


def node_text(node: NodeRow) -> str:
    """Build the raw text string used for embedding and tokenisation.

    This is the single source of truth for *what text represents a node*.
    ``similarity.node_text_tokens`` delegates here so that the lexical and
    vector spaces are always aligned.
    """
    parts: list[str] = [node.label or "", node.type or ""]
    for value in (node.details or {}).values():
        text = str(value or "").strip()
        if text.lower() in _LOW_SIGNAL:
            continue
        parts.append(text)
    for section in node.card_sections or []:
        if isinstance(section, dict):
            parts.append(str(section.get("title", "")))
            parts.append(str(section.get("content", ""))[:_SECTION_CONTENT_CAP])
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Backfill helper
# ---------------------------------------------------------------------------


def embed_graph_nodes(
    store: Any,
    graph_id: str,
    model: EmbeddingModel,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Embed all nodes in *graph_id* that do not yet have an embedding.

    Args:
        store: A ``GraphStore`` (or compatible duck-type with ``list_nodes``
               and ``upsert_embedding`` and ``embedding_repo.has_embedding``).
        graph_id: The graph to backfill.
        model: The embedding model to use.
        dry_run: When ``True``, count would-be embeddings but write nothing.

    Returns:
        ``{"embedded": int, "skipped": int, "dry_run": bool}`` in normal mode.
        ``{"embedded": 0, "skipped": 0, "would_embed": int, "dry_run": True}``
        in dry-run mode.
    """
    nodes: list[NodeRow] = store.query_nodes(graph_id)
    embedded = 0
    skipped = 0
    would_embed = 0

    for node in nodes:
        already = store.embedding_repo.has_embedding(graph_id, "node", node.id, model.name)
        if already:
            skipped += 1
            continue

        if dry_run:
            would_embed += 1
            continue

        text = node_text(node)
        vec = model.embed(text)
        store.upsert_embedding(graph_id, "node", node.id, model.name, vec)
        embedded += 1

    if dry_run:
        return {"embedded": 0, "skipped": 0, "would_embed": would_embed, "dry_run": True}

    return {"embedded": embedded, "skipped": skipped, "dry_run": False}
