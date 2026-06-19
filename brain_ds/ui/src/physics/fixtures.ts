/**
 * brain_ds/ui/src/physics/fixtures.ts
 *
 * Seeded LCG + deterministic fixture infrastructure for Barnes-Hut / FA2 tests.
 * Provides:
 *  - lcg(seed): seeded linear-congruential generator → deterministic float sequences
 *  - generateFixture(n, seed): stable node/edge layout for snapshot tests
 *  - FA2_500_FIXTURE / FA2_2000_FIXTURE: pre-built fixture constants
 *  - inferSettings(n): auto-tune physics config by node count
 *
 * Spec: graph-physics-fa2-quadtree / T3.1-T3.2
 */

// ── Seeded LCG (Park-Miller, 31-bit) ─────────────────────────────────────────
// Multiplier and modulus from Knuth / Park-Miller: m=2^31-1, a=16807
const LCG_M = 2147483647;  // 2^31 - 1 (Mersenne prime)
const LCG_A = 16807;       // primitive root of LCG_M

/**
 * lcg(seed) — returns a function that generates deterministic float values in [0, 1).
 * Each call advances the generator state by one step.
 * Seed must be an integer in [1, 2^31 - 2].
 */
export function lcg(seed: number): () => number {
  // Clamp seed to valid range; fold 0 to 1
  let state = ((Math.floor(Math.abs(seed)) % (LCG_M - 1)) || 1);
  return function next(): number {
    // Schrage's method for overflow-safe multiplication:
    // state = (LCG_A * state) mod LCG_M
    state = (LCG_A * state) % LCG_M;
    return (state - 1) / (LCG_M - 2);  // normalize to [0, 1)
  };
}

// ── Fixture shape ─────────────────────────────────────────────────────────────

export interface FixtureNode {
  id: string;
  x: number;
  y: number;
  degree: number;
}

export interface FixtureEdge {
  from: string;
  to: string;
}

export interface PhysicsFixture {
  nodes: FixtureNode[];
  edges: FixtureEdge[];
  seed: number;
  n: number;
}

// ── generateFixture ───────────────────────────────────────────────────────────

/**
 * generateFixture(n, seed) → stable PhysicsFixture for snapshot tests.
 *
 * Nodes are placed on a deterministic spiral; edges connect each node to
 * 3 of its near-neighbors deterministically (no randomness beyond the LCG).
 * The resulting graph is connected, planar-ish, and exercises both sparse
 * and dense repulsion paths.
 *
 * Bootstrap note: run once to generate the fixture JSON, then commit it.
 * CI snapshot tests compare against the committed values within ±0.5 px.
 */
export function generateFixture(n: number, seed: number): PhysicsFixture {
  const rng = lcg(seed);

  // Place nodes on a deterministic sunflower spiral (Vogel's method with
  // golden angle) perturbed by small LCG noise so positions are not perfectly
  // symmetric — this makes the physics non-degenerate.
  const GOLDEN = 2.399963229728653;  // 2π / φ²
  const SCALE = 20 * Math.sqrt(n);

  const nodes: FixtureNode[] = [];
  for (let i = 0; i < n; i++) {
    const r = SCALE * Math.sqrt(i / n);
    const theta = i * GOLDEN;
    const noise = (rng() - 0.5) * 8;  // ±4 px perturbation
    nodes.push({
      id: String(i),
      x: r * Math.cos(theta) + noise,
      y: r * Math.sin(theta) + (rng() - 0.5) * 8,
      degree: 0,
    });
  }

  // Connect each node to 3 neighbours in a ring (deterministic, no LCG needed)
  const edges: FixtureEdge[] = [];
  for (let i = 0; i < n; i++) {
    // Primary ring: connect i → (i+1) % n
    const j = (i + 1) % n;
    const node = nodes[i];
    const neighbor = nodes[j];
    if (!node || !neighbor) continue;
    edges.push({ from: String(i), to: String(j) });
    node.degree += 1;
    neighbor.degree += 1;

    // Skip link: connect every 7th node to i+7 for cross-cluster edges
    if (i % 3 === 0) {
      const k = (i + 7) % n;
      if (k !== i) {
        const skipNode = nodes[k];
        if (!skipNode) continue;
        edges.push({ from: String(i), to: String(k) });
        node.degree += 1;
        skipNode.degree += 1;
      }
    }
  }

  return { nodes, edges, seed, n };
}

// ── Pre-built fixture constants ────────────────────────────────────────────────

/** Canonical 500-node fixture used by CI snapshot tests. */
export const FA2_500_FIXTURE: PhysicsFixture = generateFixture(500, 0xC0FFEE);

/** Canonical 2000-node fixture used by worker-threshold tests. */
export const FA2_2000_FIXTURE: PhysicsFixture = generateFixture(2000, 0xC0FFEE);

// ── inferSettings ─────────────────────────────────────────────────────────────

export interface PhysicsConfig {
  algorithm: 'legacy' | 'fa2' | 'barnes-hut' | 'worker';
  workerThreshold: number;
  theta: number;
  maxCollisionIterations: number;
  temperature: number;
  gravity: number;
  repulsion: number;
  spring: number;
  restLength: number;
}

/**
 * inferSettings(n) → auto-tune physics config for n nodes.
 *
 * Heuristics:
 *  - n < 50    → legacy O(n²), no overhead
 *  - 50–999   → fa2 (Barnes-Hut main thread)
 *  - ≥ 1000   → worker offload
 *
 * Exposed on window.vis for template consumption.
 */
export function inferSettings(n: number): PhysicsConfig {
  const workerThreshold = 1000;

  let algorithm: PhysicsConfig['algorithm'];
  if (n < 50) {
    algorithm = 'legacy';
  } else if (n < workerThreshold) {
    algorithm = 'fa2';
  } else {
    algorithm = 'worker';
  }

  // Theta: larger graphs benefit from more aggressive approximation
  const theta = n > 500 ? 0.6 : 0.5;

  // Spring rest length scales with sqrt(n) so the graph spreads naturally
  const restLength = Math.max(80, 30 * Math.sqrt(Math.min(n, 500)));

  // Repulsion decreases with graph size (nodes are further apart on average)
  const repulsion = Math.max(400, 3600 / Math.sqrt(n / 10 + 1));

  return {
    algorithm,
    workerThreshold,
    theta,
    maxCollisionIterations: 3,
    temperature: 1.0,
    gravity: 0.002,
    repulsion,
    spring: 0.01,
    restLength,
  };
}
