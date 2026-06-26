// @ts-nocheck
/**
 * label-policy.ts — Zoom-aware label culling policy (Slice 1: graph-label-culling)
 *
 * Pure function module: no DOM, no side effects, deterministic given the same inputs.
 * Both the canvas renderer and the D4 overlay consume this module independently
 * so either path can be gated without affecting the other (D4 Overlay Independence).
 */

// ── Types ────────────────────────────────────────────────────────────────────

export type LabelReason = 'selected' | 'hovered' | 'focused' | 'pinned' | 'cluster-anchor' | 'budget' | 'culled';

export type LabelDecision = {
  visible: boolean;
  reason: LabelReason;
};

export type LabelNode = {
  id: string | number;
  label?: string;
  degree?: number;
  centrality?: number;
  selected?: boolean;
  hovered?: boolean;
  focused?: boolean;
  pinned?: boolean;
  clusterAnchor?: boolean;
};

export type LabelViewport = {
  /** Current zoom scale (1 = 100%). */
  scale: number;
};

export type LabelPriorityWeights = {
  degree?: number;
  centrality?: number;
  selected?: number;
};

export type LabelConfig = {
  /** Zoom scale below which ALL labels are culled (except always-visible). */
  zoomThreshold: number;
  /** Maximum number of labels to render per frame (budget cap). */
  budgetPerFrame: number;
  /** Multipliers for priority scoring. */
  priorityWeights: LabelPriorityWeights;
};

// ── Default config ───────────────────────────────────────────────────────────

export const DEFAULT_LABEL_CONFIG: LabelConfig = {
  zoomThreshold: 0.4,
  budgetPerFrame: 80,
  priorityWeights: {
    degree: 1.0,
    centrality: 2.0,
    selected: 100.0,
  },
};

// ── Priority scoring ─────────────────────────────────────────────────────────

function scoreNode(node: LabelNode, weights: LabelPriorityWeights): number {
  const w = weights || {};
  const degreeScore = (node.degree || 0) * (w.degree !== undefined ? w.degree : 1.0);
  const centralityScore = (node.centrality || 0) * (w.centrality !== undefined ? w.centrality : 2.0);
  const selectedScore = (node.selected ? 1 : 0) * (w.selected !== undefined ? w.selected : 100.0);
  return degreeScore + centralityScore + selectedScore;
}

// ── Always-visible predicate ─────────────────────────────────────────────────

function isAlwaysVisible(node: LabelNode): LabelReason | null {
  if (node.selected) return 'selected';
  if (node.hovered)  return 'hovered';
  if (node.focused)  return 'focused';
  if (node.pinned)   return 'pinned';
  if (node.clusterAnchor) return 'cluster-anchor';
  return null;
}

// ── Main export ──────────────────────────────────────────────────────────────

/**
 * Compute which nodes should have their label rendered this frame.
 *
 * Always-visible rules (selected | hovered | focused | pinned | clusterAnchor) override both
 * the zoom threshold and the budget cap.
 *
 * @param nodes    Array of nodes to evaluate.
 * @param viewport Current viewport state (only `scale` is consumed).
 * @param config   Policy config: zoomThreshold, budgetPerFrame, priorityWeights.
 * @returns        LabelDecision[] parallel to the input nodes array.
 */
export function computeVisibleLabels(
  nodes: LabelNode[],
  viewport: LabelViewport,
  config: LabelConfig,
): LabelDecision[] {
  const cfg = config || DEFAULT_LABEL_CONFIG;
  const belowThreshold = viewport.scale < cfg.zoomThreshold;

  // First pass: separate always-visible from candidates
  const decisions: LabelDecision[] = new Array(nodes.length);
  const candidateIndices: number[] = [];

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    const alwaysReason = isAlwaysVisible(node);
    if (alwaysReason !== null) {
      // Always-visible: bypass zoom threshold and budget
      decisions[i] = { visible: true, reason: alwaysReason };
    } else if (belowThreshold) {
      // Below threshold: cull everything that isn't always-visible
      decisions[i] = { visible: false, reason: 'culled' };
    } else {
      // Candidate for budget-based culling
      decisions[i] = { visible: false, reason: 'culled' }; // placeholder
      candidateIndices.push(i);
    }
  }

  if (belowThreshold) {
    // No budget pass needed — all non-always-visible are culled
    return decisions;
  }

  // Second pass: rank candidates by priority and apply budget cap
  const budget = cfg.budgetPerFrame;
  const weights = cfg.priorityWeights || {};

  // Count already-committed always-visible labels against the budget
  let alwaysVisibleCount = 0;
  for (let i = 0; i < nodes.length; i++) {
    if (decisions[i].visible) alwaysVisibleCount++;
  }

  // Sort candidates by descending priority score
  candidateIndices.sort((a, b) => {
    return scoreNode(nodes[b], weights) - scoreNode(nodes[a], weights);
  });

  // Assign visible up to (budget - alwaysVisibleCount), rest are culled
  const remaining = Math.max(0, budget - alwaysVisibleCount);
  for (let k = 0; k < candidateIndices.length; k++) {
    const idx = candidateIndices[k];
    if (k < remaining) {
      decisions[idx] = { visible: true, reason: 'budget' };
    } else {
      decisions[idx] = { visible: false, reason: 'culled' };
    }
  }

  return decisions;
}
