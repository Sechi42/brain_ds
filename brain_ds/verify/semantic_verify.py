"""Semantic output verification for brain_ds BRD documents.

Public API:
  score_graph_faithfulness(brd_text, graph_id, store) -> FaithfulnessResult
  score_brd_coherence(brd_text, graph_id, *, language, model=None) -> CoherenceResult
  build_semantic_report(faithfulness, coherence) -> SemanticReport

This module is an INTERNAL verify function — NOT an MCP tool.
Tool count stays at 24; no TOOL_REGISTRY, grounding harness, or harness_check changes.

Design: §2 (module layout), §3 (entity extraction), §4 (LLM judge), §5 (tiering).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from brain_ds.scoring.factors import _fold_accents


# ---------------------------------------------------------------------------
# Module-level constants (tunable at one location)
# ---------------------------------------------------------------------------

FAITHFULNESS_WARN_THRESHOLD: float = 0.85
COHERENCE_MIN_SCORE: int = 3
NEEDS_DATA_SUGGEST_DENSITY: float = 0.30
SUPPORTED_DOCUMENTATION_LANGUAGES: frozenset[str] = frozenset({"en", "es"})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReferenceFinding:
    """A single entity reference extracted from BRD text."""
    raw_text: str            # the BRD span that named the entity
    matched_node_id: str | None
    matched_label: str | None
    via: str                 # "wikilink" | "normalized_label" | "unresolved"
    resolved: bool


@dataclass(frozen=True)
class FaithfulnessResult:
    """Result of the deterministic graph-grounded faithfulness layer."""
    graph_id: str
    total_references: int
    resolved_references: int
    ratio: float                        # resolved / total  (1.0 when total == 0)
    references: tuple[ReferenceFinding, ...]
    wikilink_coverage: float            # wikilinked mentions / total mentions
    needs_data_density: float           # [NEEDS DATA] markers / section count


@dataclass(frozen=True)
class CoherenceResult:
    """Result of the LLM coherence/consistency judge (gated)."""
    ran: bool                           # False when RUN_LIVE_LLM unset
    language: str
    section_scores: tuple[tuple[str, int], ...]   # (section_title, 1-5)
    consistency_pass: bool | None       # None when not run
    rationales: tuple[str, ...]


@dataclass(frozen=True)
class SemanticFinding:
    """A single finding from either the deterministic or LLM layer."""
    severity: str    # "CRITICAL" | "WARNING" | "SUGGESTION"
    dimension: str   # "faithfulness" | "consistency" | "coherence" | "wikilink" | "needs_data"
    message: str
    locator: str     # section title or referenced entity text (NOT a Path)


@dataclass(frozen=True)
class SemanticReport:
    """Combined tiered advisory report — NEVER blocks archive."""
    graph_id: str
    faithfulness: FaithfulnessResult
    coherence: CoherenceResult
    findings: tuple[SemanticFinding, ...]

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "CRITICAL" for f in self.findings)

    @property
    def has_warning(self) -> bool:
        return any(f.severity == "WARNING" for f in self.findings)


# ---------------------------------------------------------------------------
# JudgeModel Protocol — injection seam for chat-completion client
# ---------------------------------------------------------------------------

@runtime_checkable
class JudgeModel(Protocol):
    """Minimal protocol for the LLM coherence judge.

    Production wiring is DEFERRED (v2). In v1 the live path raises
    NotImplementedError — exercised only via RUN_LIVE_LLM with an injected stub.
    """

    def complete(self, prompt: str) -> str:
        ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_NEEDS_DATA_RE = re.compile(r"\[NEEDS DATA\]")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def _normalize_label(text: str) -> str:
    """Normalize a node label for comparison with FTS normalization.

    Delegates to _fold_accents (NFKD + combining-char strip) then lowercases
    and collapses whitespace — matching the FTS5 normalization contract at
    graph_store.py:313-314 (NFD + Mn-strip + lower).

    This is the single accent-folding source of truth for the faithfulness
    scorer. The parity guard test (test_normalize_label_parity_with_fts)
    asserts byte-identical output vs. applying _fold_accents + lower + split.
    """
    folded = _fold_accents(text)
    return " ".join(folded.lower().split())


def _build_label_index(nodes: list) -> dict[str, tuple[str, str]]:
    """Build normalized-label -> (node_id, original_label) index from NodeRow list."""
    index: dict[str, tuple[str, str]] = {}
    for node in nodes:
        key = _normalize_label(node.label)
        if key:
            index[key] = (node.id, node.label)
    return index


def _count_sections(brd_text: str) -> int:
    """Count markdown headings (## level) in BRD text. Minimum 1 to avoid div-by-zero."""
    count = len(_HEADING_RE.findall(brd_text))
    return max(count, 1)


# ---------------------------------------------------------------------------
# Pass A + B: Entity extraction and resolution
# ---------------------------------------------------------------------------

def _extract_wikilinks(brd_text: str) -> list[str]:
    """Extract all [[...]] inner texts in order."""
    return _WIKILINK_RE.findall(brd_text)


def _extract_plain_mentions(brd_text: str, label_index: dict[str, tuple[str, str]], wikilinked_keys: set[str]) -> list[str]:
    """Pass B: find plain-text occurrences of node labels not already covered by wikilinks.

    Length guard: only labels with >= 2 normalized tokens OR >= 4 chars qualify
    (suppresses noise from short/generic labels).
    """
    mentions: list[str] = []
    # Strip wikilinks from text to avoid double-counting
    stripped = _WIKILINK_RE.sub("", brd_text)

    for norm_label, (node_id, orig_label) in label_index.items():
        if norm_label in wikilinked_keys:
            continue  # already counted in wikilink pass

        tokens = norm_label.split()
        if len(tokens) < 2 and len(norm_label) < 4:
            continue  # length guard

        # Word-boundary anchored search on normalized text
        normalized_text = _normalize_label(stripped)
        pattern = r"(?<!\w)" + re.escape(norm_label) + r"(?!\w)"
        if re.search(pattern, normalized_text):
            mentions.append(orig_label)

    return mentions


# ---------------------------------------------------------------------------
# Public: score_graph_faithfulness
# ---------------------------------------------------------------------------

def score_graph_faithfulness(
    brd_text: str,
    graph_id: str,
    store,
) -> FaithfulnessResult:
    """Deterministic graph-grounded faithfulness scorer.

    Pass A: wikilinks (authoritative).
    Pass B: plain-text label mentions (supplementary, precision-guarded).

    No LLM call. No network I/O. Operates purely on text + SQLite queries.
    """
    # Load all nodes once — one query, no per-reference round-trips
    nodes = store.query_nodes(graph_id)
    label_index = _build_label_index(nodes)

    # --- Pass A: wikilink extraction ---
    wikilink_texts = _extract_wikilinks(brd_text)
    wikilinked_keys: set[str] = set()
    references: list[ReferenceFinding] = []

    for raw in wikilink_texts:
        key = _normalize_label(raw)
        wikilinked_keys.add(key)
        if key in label_index:
            node_id, orig_label = label_index[key]
            references.append(ReferenceFinding(
                raw_text=raw,
                matched_node_id=node_id,
                matched_label=orig_label,
                via="wikilink",
                resolved=True,
            ))
        else:
            # Not in exact index — try FTS as confirmer
            fts_hits = store.search_nodes_fts(graph_id, raw)
            if fts_hits:
                # Resolve with the first FTS hit
                node_id = fts_hits[0]
                matching_node = next((n for n in nodes if n.id == node_id), None)
                references.append(ReferenceFinding(
                    raw_text=raw,
                    matched_node_id=node_id,
                    matched_label=matching_node.label if matching_node else None,
                    via="wikilink",
                    resolved=True,
                ))
            else:
                references.append(ReferenceFinding(
                    raw_text=raw,
                    matched_node_id=None,
                    matched_label=None,
                    via="wikilink",
                    resolved=False,
                ))

    wikilink_count = len(references)

    # --- Pass B: plain-text mentions ---
    plain_mentions = _extract_plain_mentions(brd_text, label_index, wikilinked_keys)
    for orig_label in plain_mentions:
        norm = _normalize_label(orig_label)
        node_id, matched_label = label_index.get(norm, (None, None))
        references.append(ReferenceFinding(
            raw_text=orig_label,
            matched_node_id=node_id,
            matched_label=matched_label,
            via="normalized_label",
            resolved=node_id is not None,
        ))

    total = len(references)
    resolved = sum(1 for r in references if r.resolved)
    ratio = (resolved / total) if total > 0 else 1.0

    # --- Sub-metrics ---
    total_mentions = wikilink_count + len(plain_mentions)
    wikilink_coverage = (wikilink_count / total_mentions) if total_mentions > 0 else 1.0

    needs_data_count = len(_NEEDS_DATA_RE.findall(brd_text))
    section_count = _count_sections(brd_text)
    needs_data_density = needs_data_count / section_count

    return FaithfulnessResult(
        graph_id=graph_id,
        total_references=total,
        resolved_references=resolved,
        ratio=ratio,
        references=tuple(references),
        wikilink_coverage=wikilink_coverage,
        needs_data_density=needs_data_density,
    )


# ---------------------------------------------------------------------------
# Public: score_brd_coherence
# ---------------------------------------------------------------------------

def score_brd_coherence(
    brd_text: str,
    graph_id: str,
    *,
    language: str,
    model: JudgeModel | None = None,
) -> CoherenceResult:
    """LLM coherence/consistency judge — gated behind RUN_LIVE_LLM.

    Returns CoherenceResult(ran=False) when RUN_LIVE_LLM is unset.
    Raises ValueError for unsupported languages.
    The live path raises NotImplementedError — production wiring is DEFERRED (v2).
    """
    # Language validation runs before gating check — always raises ValueError for bad lang
    if language not in SUPPORTED_DOCUMENTATION_LANGUAGES:
        raise ValueError(
            f"Unsupported language {language!r}. "
            f"Supported: {sorted(SUPPORTED_DOCUMENTATION_LANGUAGES)}"
        )

    if not os.environ.get("RUN_LIVE_LLM"):
        return CoherenceResult(
            ran=False,
            language=language,
            section_scores=(),
            consistency_pass=None,
            rationales=(),
        )

    # Live path — requires an injected JudgeModel
    if model is None:
        raise NotImplementedError(
            "live path: inject a JudgeModel satisfying complete(prompt: str) -> str. "
            "Production chat-client wiring is deferred to v2."
        )

    # Invoke the judge (separate calls to limit halo effect)
    # Coherence score per section
    section_scores: list[tuple[str, int]] = []
    headings = [m.group(0).strip() for m in _HEADING_RE.finditer(brd_text)]
    rationales: list[str] = []

    for heading in headings:
        prompt = (
            f"[{language}] Rate the internal coherence of the section '{heading}' "
            f"in this BRD on a scale of 1-5 (5=excellent). "
            f"Respond with JSON: {{\"score\": <int>, \"rationale\": \"<str>\"}}.\n\n{brd_text}"
        )
        raw = model.complete(prompt)
        try:
            import json
            parsed = json.loads(raw)
            score = int(parsed.get("score", 3))
            rationale = str(parsed.get("rationale", ""))
        except Exception:
            score = 3
            rationale = raw
        section_scores.append((heading, score))
        rationales.append(rationale)

    # Cross-section consistency
    consistency_prompt = (
        f"[{language}] Does this BRD have cross-section consistency? "
        f"Do Solutions address the stated Problems? "
        f"Respond with JSON: {{\"pass\": true/false, \"rationale\": \"<str>\"}}.\n\n{brd_text}"
    )
    consistency_raw = model.complete(consistency_prompt)
    try:
        import json
        parsed_c = json.loads(consistency_raw)
        consistency_pass = bool(parsed_c.get("pass", True))
        rationales.append(str(parsed_c.get("rationale", "")))
    except Exception:
        consistency_pass = True
        rationales.append(consistency_raw)

    return CoherenceResult(
        ran=True,
        language=language,
        section_scores=tuple(section_scores),
        consistency_pass=consistency_pass,
        rationales=tuple(rationales),
    )


# ---------------------------------------------------------------------------
# Public: build_semantic_report
# ---------------------------------------------------------------------------

def build_semantic_report(
    faithfulness: FaithfulnessResult,
    coherence: CoherenceResult,
) -> SemanticReport:
    """Aggregate FaithfulnessResult + CoherenceResult into a tiered SemanticReport.

    Tier rules (§5 of design):
    - faithfulness: any resolved=False -> CRITICAL
    - faithfulness: ratio < 0.85 but all resolved -> WARNING
    - wikilink: wikilink_coverage < 1.0 -> SUGGESTION
    - needs_data: density > NEEDS_DATA_SUGGEST_DENSITY -> SUGGESTION
    - consistency (LLM, ran=True): consistency_pass=False -> WARNING
    - coherence (LLM, ran=True): section_score < COHERENCE_MIN_SCORE -> WARNING
    - coherence (LLM, ran=True): section_score in [COHERENCE_MIN_SCORE, 4] -> SUGGESTION
    """
    findings: list[SemanticFinding] = []

    # --- Deterministic layer ---

    # CRITICAL: any unresolved reference
    for ref in faithfulness.references:
        if not ref.resolved:
            findings.append(SemanticFinding(
                severity="CRITICAL",
                dimension="faithfulness",
                message=f"Entity reference '{ref.raw_text}' could not be resolved to any graph node.",
                locator=ref.raw_text,
            ))

    # WARNING: low ratio but all resolve (no CRITICAL)
    unresolved_count = sum(1 for r in faithfulness.references if not r.resolved)
    if (
        unresolved_count == 0
        and faithfulness.total_references > 0
        and faithfulness.ratio < FAITHFULNESS_WARN_THRESHOLD
    ):
        findings.append(SemanticFinding(
            severity="WARNING",
            dimension="faithfulness",
            message=(
                f"Faithfulness ratio {faithfulness.ratio:.2f} is below threshold "
                f"{FAITHFULNESS_WARN_THRESHOLD} (all references resolve, but ratio is low)."
            ),
            locator=f"graph:{faithfulness.graph_id}",
        ))

    # SUGGESTION: unwikilinked entity mentions
    if faithfulness.wikilink_coverage < 1.0:
        findings.append(SemanticFinding(
            severity="SUGGESTION",
            dimension="wikilink",
            message=(
                f"Wikilink coverage is {faithfulness.wikilink_coverage:.0%}. "
                "Some entity mentions are plain text — consider adding [[wikilinks]]."
            ),
            locator=f"graph:{faithfulness.graph_id}",
        ))

    # SUGGESTION: high [NEEDS DATA] density
    if faithfulness.needs_data_density > NEEDS_DATA_SUGGEST_DENSITY:
        findings.append(SemanticFinding(
            severity="SUGGESTION",
            dimension="needs_data",
            message=(
                f"[NEEDS DATA] density is {faithfulness.needs_data_density:.2f} markers/section "
                f"(threshold {NEEDS_DATA_SUGGEST_DENSITY}). Consider completing sparse sections."
            ),
            locator=f"graph:{faithfulness.graph_id}",
        ))

    # --- LLM layer (only when coherence.ran is True) ---
    if coherence.ran:
        # WARNING: cross-section inconsistency
        if coherence.consistency_pass is False:
            findings.append(SemanticFinding(
                severity="WARNING",
                dimension="consistency",
                message="Cross-section consistency check failed: Solutions may not address stated Problems.",
                locator=f"graph:{faithfulness.graph_id}",
            ))

        # Section-level coherence scores
        for section_title, score in coherence.section_scores:
            if score < COHERENCE_MIN_SCORE:
                findings.append(SemanticFinding(
                    severity="WARNING",
                    dimension="coherence",
                    message=f"Section '{section_title}' has low coherence score ({score}/5).",
                    locator=section_title,
                ))
            elif score <= 4:
                # Score is in [COHERENCE_MIN_SCORE, 4] → SUGGESTION
                findings.append(SemanticFinding(
                    severity="SUGGESTION",
                    dimension="coherence",
                    message=f"Section '{section_title}' has borderline coherence score ({score}/5); consider improving.",
                    locator=section_title,
                ))

    return SemanticReport(
        graph_id=faithfulness.graph_id,
        faithfulness=faithfulness,
        coherence=coherence,
        findings=tuple(findings),
    )
