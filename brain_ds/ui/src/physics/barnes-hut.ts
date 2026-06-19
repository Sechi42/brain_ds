// @ts-nocheck
/**
 * brain_ds/ui/src/physics/barnes-hut.ts
 *
 * Pure Barnes-Hut quadtree n-body repulsion.
 * No DOM / Worker imports — testable on the main thread and eval'd by Node test harness.
 *
 * Written as plain JS with JSDoc types (no TS annotation syntax) so Node can
 * eval this file directly without a transpiler step.
 *
 * API:
 *   buildQuadtree(nodes, opts)    → QuadtreeCell (root)
 *   computeBarnesHutRepulsion(nodes, qt, opts) → Force[]
 *   applyRepulsion(nodes, opts)   → void (builds + applies in one call)
 *
 * Spec: graph-physics-fa2-quadtree / T3.3-T3.4
 */

// ── LCG constants ─────────────────────────────────────────────────────────────
// (Shared with fixtures.ts conceptually; duplicated here so barnes-hut is self-contained)

// ── Quadtree ──────────────────────────────────────────────────────────────────

const DEFAULT_THETA = 0.5;
const DEFAULT_REPULSION = 3600;

/**
 * @param {number} x
 * @param {number} y
 * @param {number} w
 * @param {number} h
 * @returns {{ x, y, w, h, mass, cx, cy, body, children }}
 */
function makeCell(x, y, w, h) {
  return { x, y, w, h, mass: 0, cx: 0, cy: 0, body: null, children: null };
}

/**
 * Insert a node into the quadtree, splitting cells as needed.
 * @param {{ x, y, w, h, mass, cx, cy, body, children }} cell
 * @param {{ id, x, y, vx, vy, fixed }} node
 * @param {number} depth
 */
function qtInsert(cell, node, depth) {
  if (depth > 64) return; // Safety cap

  if (cell.mass === 0) {
    cell.body = node;
    cell.mass = 1;
    cell.cx = node.x;
    cell.cy = node.y;
    return;
  }

  // Update center of mass
  const newMass = cell.mass + 1;
  cell.cx = (cell.cx * cell.mass + node.x) / newMass;
  cell.cy = (cell.cy * cell.mass + node.y) / newMass;
  cell.mass = newMass;

  if (cell.children === null) {
    const hw = cell.w / 2;
    const hh = cell.h / 2;
    cell.children = [
      makeCell(cell.x,      cell.y,      hw, hh), // NW
      makeCell(cell.x + hw, cell.y,      hw, hh), // NE
      makeCell(cell.x,      cell.y + hh, hw, hh), // SW
      makeCell(cell.x + hw, cell.y + hh, hw, hh), // SE
    ];
    if (cell.body !== null) {
      qtInsert(qtChildFor(cell, cell.body), cell.body, depth + 1);
      cell.body = null;
    }
  }
  qtInsert(qtChildFor(cell, node), node, depth + 1);
}

function qtChildFor(cell, node) {
  const mx = cell.x + cell.w / 2;
  const my = cell.y + cell.h / 2;
  const idx = (node.x >= mx ? 1 : 0) + (node.y >= my ? 2 : 0);
  return cell.children[idx];
}

/**
 * buildQuadtree(nodes, opts) — insert all nodes and return the root cell.
 * @param {Array<{id, x, y, vx, vy}>} nodes
 * @param {{ theta?: number, repulsion?: number }} [opts]
 * @returns {object} root QuadtreeCell
 */
export function buildQuadtree(nodes, opts) {
  if (!nodes || nodes.length === 0) {
    return makeCell(-500, -500, 1000, 1000);
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.x < minX) minX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.x > maxX) maxX = n.x;
    if (n.y > maxY) maxY = n.y;
  }
  const margin = 1;
  const size = Math.max(maxX - minX, maxY - minY) + margin * 2;
  const root = makeCell(minX - margin, minY - margin, size, size);
  for (let i = 0; i < nodes.length; i++) {
    qtInsert(root, nodes[i], 0);
  }
  return root;
}

function bhRepulsionFrom(cell, body, theta, repulsion, out) {
  if (cell.mass === 0) return;

  if (cell.children === null) {
    if (cell.body === body || cell.body === null) return;
    const dx = body.x - cell.body.x;
    const dy = body.y - cell.body.y;
    const distSq = (dx * dx + dy * dy) || 0.01;
    const dist = Math.sqrt(distSq);
    const force = repulsion / distSq;
    out.fx += (dx / dist) * force;
    out.fy += (dy / dist) * force;
    return;
  }

  const dx = body.x - cell.cx;
  const dy = body.y - cell.cy;
  const distSq = (dx * dx + dy * dy) || 0.01;
  const dist = Math.sqrt(distSq);

  if (cell.w / dist < theta) {
    const force = repulsion * cell.mass / distSq;
    out.fx += (dx / dist) * force;
    out.fy += (dy / dist) * force;
  } else {
    for (let k = 0; k < 4; k++) {
      if (cell.children[k] !== null) {
        bhRepulsionFrom(cell.children[k], body, theta, repulsion, out);
      }
    }
  }
}

/**
 * computeBarnesHutRepulsion(nodes, qt, opts) → Force[]
 * Returns one {fx, fy} per node. Does NOT modify node positions.
 */
export function computeBarnesHutRepulsion(nodes, qt, opts) {
  const theta = (opts && opts.theta !== undefined) ? opts.theta : DEFAULT_THETA;
  const repulsion = (opts && opts.repulsion !== undefined) ? opts.repulsion : DEFAULT_REPULSION;
  const forces = new Array(nodes.length);
  for (let i = 0; i < nodes.length; i++) {
    const out = { fx: 0, fy: 0 };
    bhRepulsionFrom(qt, nodes[i], theta, repulsion, out);
    forces[i] = out;
  }
  return forces;
}

/**
 * applyRepulsion(nodes, opts) — build quadtree + apply repulsion to node.vx/vy.
 * Convenience wrapper for LayoutStrategy main-thread path.
 */
export function applyRepulsion(nodes, opts) {
  const theta = (opts && opts.theta !== undefined) ? opts.theta : DEFAULT_THETA;
  const repulsion = (opts && opts.repulsion !== undefined) ? opts.repulsion : DEFAULT_REPULSION;
  const dragPulls = (opts && opts.dragPulls instanceof Map) ? opts.dragPulls : null;
  const qt = buildQuadtree(nodes, opts);
  const out = { fx: 0, fy: 0 };
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.fixed) continue;
    if (dragPulls) {
      const pull = dragPulls.get(String(n.id));
      if (!(pull > 0)) {
        n.vx = 0;
        n.vy = 0;
        continue;
      }
    }
    out.fx = 0;
    out.fy = 0;
    bhRepulsionFrom(qt, n, theta, repulsion, out);
    n.vx = (n.vx || 0) + out.fx;
    n.vy = (n.vy || 0) + out.fy;
  }
}
