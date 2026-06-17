"""Pure node-text assembly — no ML imports.

Single source of truth for the text representation of a node used by both
the lexical (similarity.py) and vector (embedder.py) paths.  Keeping this
in its own module means importing ``brain_ds.scoring.similarity`` does NOT
drag fastembed / onnxruntime / numpy into the process.
"""

from __future__ import annotations

from brain_ds.store.models import NodeRow

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
