// @ts-nocheck
/**
 * brain_ds/ui/src/physics/layout-adapter.ts
 *
 * LayoutStrategy — unified physics dispatch layer.
 *
 * Written as plain JS with JSDoc types so Node can eval this file directly
 * (same pattern as live-sync.ts).
 *
 * Modes:
 *  'legacy'      → O(n²) repulsion (existing renderer._applyForces path)
 *  'barnes-hut'  → main-thread Barnes-Hut via applyRepulsion (from barnes-hut)
 *  'fa2'         → alias for 'barnes-hut' (same path)
 *  'worker'      → FA2 worker offload (above workerThreshold)
 *
 * Preserves existing renderer contracts:
 *  - drag pinning (fixed/dragNodeId nodes skipped)
 *  - temperature cooling (caller drives; passed in state.temperature)
 *  - reduced-motion gating (caller's responsibility)
 *
 * Spec: graph-physics-fa2-quadtree / T3.7-T3.8 / T3.9-T3.10 / T3.11-T3.12
 */

/**
 * @typedef {'legacy'|'barnes-hut'|'forceatlas2'|'worker'} LayoutMode
 */

export class LayoutStrategy {
  /**
   * @param {{ algorithm?: string, workerThreshold?: number, theta?: number,
   *            temperature?: number, repulsion?: number, spring?: number,
   *            restLength?: number, gravity?: number, damping?: number,
   *            maxSpeed?: number, collision?: boolean,
   *            maxCollisionIterations?: number }} [opts]
   */
  constructor(opts) {
    const o = opts || {};
    this.workerThreshold = o.workerThreshold !== undefined ? o.workerThreshold : 1000;
    this.theta = o.theta !== undefined ? o.theta : 0.5;
    this.repulsion = o.repulsion !== undefined ? o.repulsion : 3600;
    this.spring = o.spring !== undefined ? o.spring : 0.01;
    this.restLength = o.restLength !== undefined ? o.restLength : 180;
    this.gravity = o.gravity !== undefined ? o.gravity : 0.0024;
    this.damping = o.damping !== undefined ? o.damping : 0.9;
    this.maxSpeed = o.maxSpeed !== undefined ? o.maxSpeed : 120;
    this.temperature = o.temperature !== undefined ? o.temperature : 1.0;
    this._runCollision = o.collision !== undefined ? o.collision : true;
    this.maxCollisionIterations = Math.min(3, o.maxCollisionIterations !== undefined ? o.maxCollisionIterations : 3);

    // _fallbackLogged: track so we warn only once on failure
    this._fallbackLogged = false;
    this._worker = null;
    this._workerPending = false;

    // Determine initial mode
    const alg = (o.algorithm || 'fa2').toLowerCase();
    if (alg === 'legacy') {
      this.mode = 'legacy';
    } else if (alg === 'worker') {
      this.mode = 'worker';
    } else {
      // 'fa2', 'barnes-hut', or anything else → Barnes-Hut main-thread
      this.mode = 'barnes-hut';
    }
  }

  /**
   * tick(state, dt) — advance simulation by one time step.
   *
   * @param {{ nodes: Array, edges: Array, dragNodeId?: string|null,
   *            dragPulls?: Map, temperature?: number }} state
   * @param {number} dt  elapsed time in seconds
   */
  tick(state, dt) {
    const nodes = state.nodes;
    const edges = state.edges;
    const n = nodes.length;
    const temperature = state.temperature !== undefined ? state.temperature : this.temperature;
    const dragIsolationActive = Boolean(state.dragPulls);

    // Determine effective mode for this tick
    let effectiveMode = this.mode;
    if (this.mode !== 'legacy') {
      // Upgrade to worker if above threshold; stay on main thread below
      effectiveMode = (n >= this.workerThreshold) ? 'worker' : 'barnes-hut';
    }

    if (dragIsolationActive) {
      this._suspendWorker();
    }

    if (effectiveMode === 'worker' && !dragIsolationActive) {
      this._tickWorker(state, dt, temperature);
      return;
    }

    if (effectiveMode === 'legacy') {
      this._tickLegacy(nodes, edges, dt, temperature, state.dragNodeId, state.dragPulls);
      return;
    }

    // Barnes-Hut path (default for n < workerThreshold)
    try {
      this._bhRepulsion(nodes, edges, dt, temperature, state.dragNodeId, state.dragPulls);
    } catch (e) {
      if (!this._fallbackLogged) {
        console.warn('[LayoutStrategy] Barnes-Hut failed, falling back to legacy O(n²):', e);
        this._fallbackLogged = true;
      }
      this.mode = 'legacy';
      this._tickLegacy(nodes, edges, dt, temperature, state.dragNodeId, state.dragPulls);
    }
  }

  _suspendWorker() {
    if (this._worker && typeof this._worker.terminate === 'function') {
      try {
        this._worker.terminate();
      } catch (e) {
        // noop
      }
    }
    this._worker = null;
    this._workerPending = false;
  }

  /**
   * seed(nodes, edges) — position NEW nodes only; existing coordinates preserved.
   * New nodes are seeded near their first-edge neighbor.
   *
   * @param {Array<{id, x?, y?, vx, vy}>} nodes
   * @param {Array<{from, to}>} edges
   */
  seed(nodes, edges) {
    // Build neighbor index
    const neighborOf = new Map();
    for (let e = 0; e < edges.length; e++) {
      const from = String(edges[e].from || edges[e].source || '');
      const to = String(edges[e].to || edges[e].target || '');
      if (!neighborOf.has(from)) neighborOf.set(from, []);
      if (!neighborOf.has(to)) neighborOf.set(to, []);
      neighborOf.get(from).push(to);
      neighborOf.get(to).push(from);
    }

    // Index already-positioned nodes
    const positioned = new Map();
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (n.x !== undefined && n.y !== undefined) positioned.set(String(n.id), n);
    }

    // Seed only unpositioned nodes
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (n.x !== undefined && n.y !== undefined) continue;

      const neighbors = neighborOf.get(String(n.id)) || [];
      let placed = false;
      for (let j = 0; j < neighbors.length; j++) {
        const nbr = positioned.get(neighbors[j]);
        if (nbr) {
          const angle = Math.PI * 2 * ((i * 1.618033) % 1);
          const dist = 30 + (i % 5) * 8;
          n.x = nbr.x + Math.cos(angle) * dist;
          n.y = nbr.y + Math.sin(angle) * dist;
          n.vx = 0;
          n.vy = 0;
          positioned.set(String(n.id), n);
          placed = true;
          break;
        }
      }

      if (!placed) {
        n.x = (i % 50) * 30 - 750;
        n.y = Math.floor(i / 50) * 30 - 375;
        n.vx = 0;
        n.vy = 0;
        positioned.set(String(n.id), n);
      }
    }
  }

  // ── Barnes-Hut main-thread path ────────────────────────────────────────────

  _bhRepulsion(nodes, edges, dt, temperature, dragNodeId, dragPulls) {
    const n = nodes.length;
    const centerX = 0;
    const centerY = 0;
    const settlingAfterDrop = dragPulls && (dragNodeId === null || dragNodeId === undefined);

    const incident = new Map();
    for (let e = 0; e < edges.length; e++) {
      const from = String(edges[e].from || edges[e].source || '');
      const to = String(edges[e].to || edges[e].target || '');
      if (!incident.has(from)) incident.set(from, []);
      if (!incident.has(to)) incident.set(to, []);
      incident.get(from).push(to);
      incident.get(to).push(from);
    }
    const nodesById = new Map();
    for (let p = 0; p < n; p++) nodesById.set(String(nodes[p].id), nodes[p]);

    // Apply Barnes-Hut repulsion (adds to vx/vy)
    // applyRepulsion is expected to be in scope from barnes-hut.ts when both
    // are eval'd together. When running standalone, fall back to O(n²).
    if (typeof applyRepulsion === "function") {
      applyRepulsion(nodes, { theta: this.theta, repulsion: this.repulsion, dragPulls });
    } else {
      // Inline O(n²) repulsion as safe fallback
      const cutoffSq = 480 * 480;
      for (let i = 0; i < n; i++) {
        const a = nodes[i];
        if (a.fixed) continue;
        for (let j = 0; j < n; j++) {
          if (i === j) continue;
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distSq = (dx * dx + dy * dy) || 0.01;
          if (distSq > cutoffSq) continue;
          const dist = Math.sqrt(distSq);
          const force = this.repulsion / distSq;
          a.vx = (a.vx || 0) + (dx / dist) * force;
          a.vy = (a.vy || 0) + (dy / dist) * force;
        }
      }
    }

    // Spring forces + gravity + velocity integration
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      if (a.fixed) continue;
      if (dragNodeId !== null && dragNodeId !== undefined && String(a.id) === String(dragNodeId)) continue;
      if (dragPulls) {
        const pull = dragPulls.get(String(a.id));
        if (!(pull > 0)) {
          a.vx = 0;
          a.vy = 0;
          continue;
        }
      }

      let fx = a.vx || 0;
      let fy = a.vy || 0;

      const linked = incident.get(String(a.id)) || [];
      for (let k = 0; k < linked.length; k++) {
        const other = nodesById.get(linked[k]);
        if (!other) continue;
        const sx = other.x - a.x;
        const sy = other.y - a.y;
        const sl = Math.sqrt(sx * sx + sy * sy) || 0.01;
        const hooke = this.spring * (sl - this.restLength);
        fx += (sx / sl) * hooke;
        fy += (sy / sl) * hooke;
      }

      fx += (centerX - a.x) * this.gravity;
      fy += (centerY - a.y) * this.gravity;

      let vx = fx * this.damping;
      let vy = fy * this.damping;
      if (settlingAfterDrop) {
        vx *= 0.3;
        vy *= 0.3;
      }
      const speed = Math.abs(vx) + Math.abs(vy);
      if (speed > this.maxSpeed) { vx *= this.maxSpeed / speed; vy *= this.maxSpeed / speed; }
      else if (speed < 0.02) { vx = 0; vy = 0; }

      a.vx = vx;
      a.vy = vy;

      let moveScale = 1;
      if (dragPulls) {
        const pull = dragPulls.get(String(a.id));
        moveScale = pull === undefined ? 0 : pull;
      }
      a.x += vx * temperature * moveScale;
      a.y += vy * temperature * moveScale;
    }
  }

  // ── Legacy O(n²) path ─────────────────────────────────────────────────────

  _tickLegacy(nodes, edges, dt, temperature, dragNodeId, dragPulls) {
    const n = nodes.length;
    const centerX = 0;
    const centerY = 0;
    const cutoffSq = 480 * 480;
    const settlingAfterDrop = dragPulls && (dragNodeId === null || dragNodeId === undefined);

    const incident = new Map();
    for (let e = 0; e < edges.length; e++) {
      const from = String(edges[e].from || edges[e].source || '');
      const to = String(edges[e].to || edges[e].target || '');
      if (!incident.has(from)) incident.set(from, []);
      if (!incident.has(to)) incident.set(to, []);
      incident.get(from).push(to);
      incident.get(to).push(from);
    }
    const nodesById = new Map();
    for (let p = 0; p < n; p++) nodesById.set(String(nodes[p].id), nodes[p]);

    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      if (a.fixed) continue;
      if (dragNodeId !== null && dragNodeId !== undefined && String(a.id) === String(dragNodeId)) continue;
      if (dragPulls) {
        const pull = dragPulls.get(String(a.id));
        if (!(pull > 0)) {
          a.vx = 0;
          a.vy = 0;
          continue;
        }
      }

      let fx = 0; let fy = 0;

      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const b = nodes[j];
        const dx = a.x - b.x; const dy = a.y - b.y;
        const distSq = (dx * dx + dy * dy) || 0.01;
        if (distSq > cutoffSq) continue;
        const dist = Math.sqrt(distSq);
        const force = this.repulsion / distSq;
        fx += (dx / dist) * force; fy += (dy / dist) * force;
      }

      const linked = incident.get(String(a.id)) || [];
      for (let k = 0; k < linked.length; k++) {
        const other = nodesById.get(linked[k]);
        if (!other) continue;
        const sx = other.x - a.x; const sy = other.y - a.y;
        const sl = Math.sqrt(sx * sx + sy * sy) || 0.01;
        const hooke = this.spring * (sl - this.restLength);
        fx += (sx / sl) * hooke; fy += (sy / sl) * hooke;
      }

      fx += (centerX - a.x) * this.gravity;
      fy += (centerY - a.y) * this.gravity;

      let vx = ((a.vx || 0) + fx * dt) * this.damping;
      let vy = ((a.vy || 0) + fy * dt) * this.damping;
      if (settlingAfterDrop) {
        vx *= 0.3;
        vy *= 0.3;
      }
      const speed = Math.abs(vx) + Math.abs(vy);
      if (speed > this.maxSpeed) { vx *= this.maxSpeed / speed; vy *= this.maxSpeed / speed; }
      else if (speed < 0.02) { vx = 0; vy = 0; }

      a.vx = vx; a.vy = vy;

      let moveScale = 1;
      if (dragPulls) {
        const pull = dragPulls.get(String(a.id));
        moveScale = pull === undefined ? 0 : pull;
      }
      a.x += vx * temperature * moveScale;
      a.y += vy * temperature * moveScale;
    }
  }

  // ── Worker path ────────────────────────────────────────────────────────────

  _tickWorker(state, dt, temperature) {
    if (this._workerPending) return;

    if (this._worker === null) {
      try {
        this._worker = new Worker('/physics-worker.js');
        this._worker.onmessage = (e) => {
          const positions = e.data && e.data.positions;
          if (positions && Array.isArray(positions)) {
            const nodes = state.nodes;
            for (let i = 0; i < nodes.length && i < positions.length; i++) {
              if (!nodes[i].fixed) {
                nodes[i].x = positions[i].x;
                nodes[i].y = positions[i].y;
              }
            }
          }
          this._workerPending = false;
        };
        this._worker.onerror = (err) => {
          if (!this._fallbackLogged) {
            console.warn('[LayoutStrategy] Worker failed, falling back to Barnes-Hut:', err);
            this._fallbackLogged = true;
          }
          this._worker = null;
          this._workerPending = false;
          this.mode = 'barnes-hut';
        };
      } catch (e) {
        if (!this._fallbackLogged) {
          console.warn('[LayoutStrategy] Worker spawn failed, falling back to Barnes-Hut:', e);
          this._fallbackLogged = true;
        }
        this._worker = null;
        this.mode = 'barnes-hut';
        try {
          this._bhRepulsion(state.nodes, state.edges, dt, temperature, state.dragNodeId, state.dragPulls);
        } catch (e2) {
          this.mode = 'legacy';
          this._tickLegacy(state.nodes, state.edges, dt, temperature, state.dragNodeId, state.dragPulls);
        }
        return;
      }
    }

    this._workerPending = true;
    this._worker.postMessage({
      nodes: state.nodes.map(n => ({ id: n.id, x: n.x, y: n.y, vx: n.vx, vy: n.vy, fixed: n.fixed })),
      edges: state.edges,
      dt,
      temperature,
      theta: this.theta,
    });

    // Worker timeout guard: 1 s → fallback
    setTimeout(() => {
      if (this._workerPending) {
        if (!this._fallbackLogged) {
          console.warn('[LayoutStrategy] Worker timed out after 1 s, falling back to Barnes-Hut');
          this._fallbackLogged = true;
        }
        this._workerPending = false;
        this.mode = 'barnes-hut';
      }
    }, 1000);
  }
}
