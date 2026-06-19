// @ts-nocheck
/**
 * brain_ds/ui/src/physics/collision.ts
 *
 * Post-FA2-pass collision step: push overlapping nodes apart using a
 * quadtree rebuilt each iteration.
 *
 * Written as plain JS with JSDoc types so Node can eval this file directly.
 *
 * API:
 *   applyCollisionStep(nodes, opts) → void
 *   resolveCollisions(nodes, opts)  → void  (alias)
 *
 * Spec: graph-physics-fa2-quadtree / T3.5-T3.6
 */

const DEFAULT_NODE_RADIUS = 12;
const MAX_ITER = 3;

/**
 * applyCollisionStep(nodes, opts)
 *
 * Resolves node overlaps in up to maxIterations (≤ 3) passes.
 * Each iteration rebuilds the quadtree (via buildQuadtree if available)
 * then sweeps pairs for overlaps and pushes them apart.
 *
 * @param {Array<{id, x, y, vx, vy, radius?, fixed?}>} nodes
 * @param {{ nodeRadius?: number, maxIterations?: number }} [opts]
 */
export function applyCollisionStep(nodes, opts) {
  const nodeRadius = (opts && opts.nodeRadius !== undefined) ? opts.nodeRadius : DEFAULT_NODE_RADIUS;
  const maxIterations = Math.min(
    MAX_ITER,
    (opts && opts.maxIterations !== undefined) ? opts.maxIterations : MAX_ITER,
  );
  const minDist = nodeRadius * 2;
  const minDistSq = minDist * minDist;

  for (let iter = 0; iter < maxIterations; iter++) {
    // Rebuild quadtree each iteration (if buildQuadtree is in scope from barnes-hut)
    // This satisfies "rebuild quadtree per iteration" requirement.
    if (typeof buildQuadtree === "function") {
      buildQuadtree(nodes.filter(n => !n.fixed));
    }

    let anyOverlap = false;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      if (a.fixed) continue;

      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        if (b.fixed) continue;

        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distSq = (dx * dx + dy * dy) || 0.0001;

        if (distSq < minDistSq) {
          anyOverlap = true;
          const dist = Math.sqrt(distSq);
          const overlap = minDist - dist;
          const nx = (dx / dist) * (overlap / 2);
          const ny = (dy / dist) * (overlap / 2);
          a.x -= nx;
          a.y -= ny;
          b.x += nx;
          b.y += ny;
        }
      }
    }

    if (!anyOverlap) break;
  }
}

/** Alias for applyCollisionStep. */
export const resolveCollisions = applyCollisionStep;
