// @ts-nocheck
/* brain_ds offline vis-compatible canvas renderer (no external dependencies) */
(function () {
  if (window.vis && window.vis.Network && window.vis.DataSet) return;

  function toArray(payload) {
    if (!payload) return [];
    return Array.isArray(payload) ? payload : [payload];
  }

  function DataSet(items) {
    this._map = new Map();
    this._listeners = [];
    this.add(items || []);
  }

  DataSet.prototype._emit = function () {
    this._listeners.forEach(function (handler) { handler(); });
  };

  DataSet.prototype._subscribe = function (handler) {
    this._listeners.push(handler);
  };

  DataSet.prototype.add = function (items) {
    toArray(items).forEach(function (item) {
      if (!item || item.id === undefined || item.id === null) return;
      this._map.set(item.id, Object.assign({}, item));
    }, this);
    this._emit();
  };

  DataSet.prototype.update = function (items) {
    toArray(items).forEach(function (item) {
      if (!item || item.id === undefined || item.id === null) return;
      var prev = this._map.get(item.id) || {};
      this._map.set(item.id, Object.assign({}, prev, item));
    }, this);
    this._emit();
  };

  DataSet.prototype.get = function (id) {
    if (id === undefined) return Array.from(this._map.values());
    return this._map.get(id);
  };

  DataSet.prototype.remove = function (items) {
    toArray(items).forEach(function (item) {
      var id = typeof item === "object" && item !== null ? item.id : item;
      if (id === undefined || id === null) return;
      this._map.delete(id);
    }, this);
    this._emit();
  };

  DataSet.prototype.clear = function () {
    this._map.clear();
    this._emit();
  };

  function Network(container, data, options) {
    this.container = container;
    this.data = data || { nodes: new DataSet([]), edges: new DataSet([]) };
    this.options = options || {};
    this.handlers = {};
    this.selectedNodeId = null;
    this.physicsEnabled = true;
    this.temperature = 1;
    this._dashOffset = 0;
    this._raf = null;
    this._lastTs = 0;
    this._activeA11yIndex = -1;
    this._prefersReducedMotion = false;
    this._reducedMotionQuery = null;
    this.hoveredNodeId = null;
    this.isDragging = false;
    this.dragNodeId = null;
    this.expandedNodeIds = new Set();
    this._hierarchyReady = false;
    this._treeFilterRootId = null;
    this._treeFilterDescendants = null;
    this._neighborIndex = new Map();
    this._frameCount = 0;
    this._d4OverlayActive = false;
    this._edgeWidthScale = 1;
    this._labelFontWeight = 400;

    // Slice 1a: viewport matrix (REQ-1.1)
    // Slice 1b: extended with vx/vy pan velocity for inertia (REQ-1.7)
    this.viewport = { scale: 1, tx: 0, ty: 0, vx: 0, vy: 0 };

    // Slice 1a: pan state — DISTINCT from isDragging/dragNodeId (REQ-1.2)
    this.isPanning = false;
    this.panStart = { x: 0, y: 0, tx0: 0, ty0: 0, lastDx: 0, lastDy: 0, lastT: 0 };

    // Slice 1b: inertia state (REQ-1.7) — DISTINCT from temperature/cooling
    this.inertiaActive = false;
    this.inertiaFriction = 0.92;
    this.minPanVelocity = 0.5;

    // Slice 3a: multi-select state (REQ-3.4) — ADDITIVE to selectedNodeId (locked literal)
    this.selectedNodeIds = new Set();
    this.keyboardFocusedNodeId = null;

    // Slice 3a: marquee selection state (REQ-3.5) — world coordinates (REQ-3.6)
    this.marquee = { active: false, x0: 0, y0: 0, x1: 0, y1: 0 };

    // Slice 3a: interaction mode tracking (design §4.2)
    this._mode = "idle"; // 'idle' | 'panning' | 'dragging-node' | 'marquee'

    // Slice 3a: suppress the browser click event that follows a marquee mouseup
    // (Chrome/Firefox fire click after mouseup even after a drag gesture on the same element)
    this._suppressNextClick = false;

    // Slice 4: hover popover state (REQ-4.1 / REQ-4.4)
    // Delay = 350 ms per spec REQ-4.1 (design §3 Slice 4 proposed 320 ms but did not
    // explicitly supersede the REQ — spec value is binding per spec §1 conventions).
    this.hoverDelayMs = 350;
    this._popoverTimer = null;
    this._popoverGraceTimer = null;  // REQ-4.2: 150 ms grace on re-entry after leave
    this._popoverNodeId = null;      // nodeId currently shown (or pending) in popover

    // Slice 6: context menu state (REQ-6.1 / design §3 Slice 6).
    // Shape from design: { open: false, x: 0, y: 0, target: null }
    // 'open' is the gate checked by _onMouseMove hover-suppression (REQ-6.10 / REQ-4.6).
    this.contextMenu = { open: false, x: 0, y: 0, target: null };
    this._themeTokens = {};

    this.container.classList.add("vis-network");
    this.container.innerHTML = "";

    this.canvas = document.createElement("canvas");
    this.canvas.className = "vis-canvas";
    this.canvas.setAttribute("role", "img");
    this.canvas.setAttribute("aria-label", "Organization graph");
    this.canvas.setAttribute("tabindex", "0");
    this.canvas.width = Math.max(640, this.container.clientWidth || 640);
    this.canvas.height = Math.max(400, this.container.clientHeight || 400);
    this.ctx = this.canvas.getContext("2d");
    this.container.appendChild(this.canvas);

    this.a11yList = document.createElement("ul");
    this.a11yList.className = "vis-a11y-sr-only";
    this.a11yList.setAttribute("aria-label", "Graph nodes");
    this.a11yList.setAttribute("role", "listbox");
    this.container.appendChild(this.a11yList);

    this.liveRegion = document.createElement("div");
    this.liveRegion.className = "vis-a11y-sr-only";
    this.liveRegion.setAttribute("aria-live", "polite");
    this.container.appendChild(this.liveRegion);

    // Slice 4: popover element — DOM, not canvas draw (REQ-4.4).
    // Injected into .vis-network container so position:absolute is relative to it.
    // ID is stable so aria-describedby on a11y list items can reference it (REQ-4.10).
    this._popoverEl = document.createElement("div");
    this._popoverEl.className = "vis-popover";
    this._popoverEl.id = "vis-hover-popover";
    this._popoverEl.setAttribute("role", "tooltip");
    this._popoverEl.setAttribute("aria-hidden", "true");
    this.container.appendChild(this._popoverEl);

    var rerender = this._wake.bind(this);
    if (this.data.nodes && this.data.nodes._subscribe) this.data.nodes._subscribe(rerender);
    if (this.data.edges && this.data.edges._subscribe) this.data.edges._subscribe(rerender);

    this.canvas.addEventListener("click", this._onClick.bind(this));
    this.canvas.addEventListener("mousemove", this._onMouseMove.bind(this));
    this.canvas.addEventListener("mousedown", this._onMouseDown.bind(this));
    this.canvas.addEventListener("mouseup", this._onMouseUp.bind(this));
    this.canvas.addEventListener("mouseleave", function () {
      this.hoveredNodeId = null;
      this._wake();
    }.bind(this));
    this.canvas.addEventListener("keydown", this._onCanvasKeydown.bind(this));
    // Slice 1b: wheel zoom handler (REQ-1.3)
    this.canvas.addEventListener("wheel", this._onWheel.bind(this), { passive: false });
    // Slice 6: context menu handler — suppress browser default + emit event (REQ-6.1)
    this.canvas.addEventListener("contextmenu", this._onContextMenu.bind(this));
    this._bindReducedMotion();
    this._refreshThemeTokens();
    this._syncModesFromOptions(this.options);
    this._wake();
  }

  Network.prototype._readCssVar = function (name, fallback) {
    try {
      var value = getComputedStyle(this.canvas).getPropertyValue(name);
      if (value && value.trim()) return value.trim();
    } catch (e) {}
    return fallback;
  };

  Network.prototype._refreshThemeTokens = function () {
    this._themeTokens = {
      panelBg: this._readCssVar("--vis-panel-bg", "#1e293b"),
      panelText: this._readCssVar("--vis-panel-text", "#e2e8f0"),
      panelBorder: this._readCssVar("--vis-panel-border", "#64748b"),
      focusRing: this._readCssVar("--vis-focus-ring", "#38bdf8"),
      stateFocusRing: this._readCssVar("--state-focus-ring", this._readCssVar("--vis-focus-ring", "#38bdf8")),
      popoverMuted: this._readCssVar("--vis-popover-muted", "#cbd5e1"),
      marqueeStroke: this._readCssVar("--vis-marquee-stroke", this._readCssVar("--vis-focus-ring", "#38bdf8")),
      marqueeFill: this._readCssVar("--vis-marquee-fill", "rgba(56,189,248,0.12)"),
      edgeDash: Number(this._readCssVar("--edge-dash", "6")) || 6,
      edgeArrowheadSize: Number(this._readCssVar("--edge-arrowhead-size", "8")) || 8,
      entityFillByType: {
        "Organization": this._readCssVar("--entity-organization-fill", "#111827"),
        "Department": this._readCssVar("--entity-department-fill", "#2563eb"),
        "Role": this._readCssVar("--entity-role-fill", "#16a34a"),
        "Data Source": this._readCssVar("--entity-data-source-fill", "#7c3aed"),
        "Heuristic": this._readCssVar("--entity-heuristic-fill", "#f59e0b"),
        "Tacit Knowledge": this._readCssVar("--entity-tacit-knowledge-fill", "#0ea5e9"),
        "Problem / Improvement Area": this._readCssVar("--entity-problem-improvement-area-fill", "#dc2626"),
        "Project": this._readCssVar("--entity-project-fill", "#4f46e5"),
        "Risk": this._readCssVar("--entity-risk-fill", "#b91c1c"),
        "Decision": this._readCssVar("--entity-decision-fill", "#0f766e"),
        "KPI": this._readCssVar("--entity-kpi-fill", "#a16207"),
        "Solution": this._readCssVar("--entity-solution-fill", "#059669"),
        "Unknown": this._readCssVar("--entity-unknown-fill", "#6b7280")
      },
      wccPalette: [
        this._readCssVar("--wcc-c0", "#3b82f6"),
        this._readCssVar("--wcc-c1", "#14b8a6"),
        this._readCssVar("--wcc-c2", "#f59e0b"),
        this._readCssVar("--wcc-c3", "#a855f7"),
        this._readCssVar("--wcc-c4", "#ef4444"),
        this._readCssVar("--wcc-c5", "#22c55e"),
        this._readCssVar("--wcc-c6", "#06b6d4"),
        this._readCssVar("--wcc-c7", "#eab308"),
        this._readCssVar("--wcc-c8", "#f97316"),
        this._readCssVar("--wcc-c9", "#10b981"),
        this._readCssVar("--wcc-c10", "#8b5cf6"),
        this._readCssVar("--wcc-c11", "#ec4899")
      ],
      outlineFallbackByTheme: {
        dark: { "Organization": true, "Project": true, "Risk": true },
        light: {}
      },
      egoEdge: this._readCssVar("--color-ego-edge", "#7c3aed")
    };
  };

  Network.prototype.refreshThemeTokens = function () {
    this._refreshThemeTokens();
    this._wake();
  };

  Network.prototype._activeThemeName = function () {
    var attr = document && document.documentElement
      ? document.documentElement.getAttribute("data-theme")
      : null;
    return attr === "light" ? "light" : "dark";
  };

  Network.prototype._resolveNodeBackground = function (node) {
    var componentId = node && node.component_id;
    if (componentId !== null && componentId !== undefined) {
      var palette = this._themeTokens.wccPalette || [];
      if (palette.length) {
        return palette[Math.abs(Number(componentId)) % palette.length];
      }
    }
    var nodeType = node && (node.type || node.group);
    if (nodeType && this._themeTokens.entityFillByType && this._themeTokens.entityFillByType[nodeType]) {
      return this._themeTokens.entityFillByType[nodeType];
    }
    var color = node && node.color;
    if (!color) return this._themeTokens.panelBg || "#1e293b";
    if (typeof color === "string") return color;
    var theme = this._activeThemeName();
    return color[theme] || color.background || color.dark || this._themeTokens.panelBg || "#1e293b";
  };

  // Slice 1a: inverse viewport transform — screen → world (REQ-1.9)
  Network.prototype._screenToWorld = function (sx, sy) {
    return {
      x: (sx - this.viewport.tx) / this.viewport.scale,
      y: (sy - this.viewport.ty) / this.viewport.scale
    };
  };

  // Slice 1a: forward viewport transform — world → screen (REQ-1.9)
  Network.prototype._worldToScreen = function (wx, wy) {
    return {
      x: wx * this.viewport.scale + this.viewport.tx,
      y: wy * this.viewport.scale + this.viewport.ty
    };
  };

  // Slice 1b: re-anchor zoom — same world point under cursor stays stationary (REQ-1.3)
  Network.prototype._applyZoom = function (sx, sy, factor) {
    var world = this._screenToWorld(sx, sy);
    var newScale = Math.max(0.25, Math.min(4.0, this.viewport.scale * factor));
    // Re-anchor: world point (wx, wy) maps back to screen (sx, sy) under new scale
    this.viewport.tx = sx - world.x * newScale;
    this.viewport.ty = sy - world.y * newScale;
    this.viewport.scale = newScale;
  };

  // Slice 1b: wheel zoom handler — preventDefault + zoom toward cursor (REQ-1.3, 1.4, 1.5, 1.12)
  Network.prototype._onWheel = function (event) {
    event.preventDefault();
    // Slice 4: dismiss popover on zoom (REQ-4.6 / OBS-4.7)
    this._hideHoverPopover();
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    // Multiplicative model: factor = 1.1^(-sign(deltaY)) (REQ-1.5)
    var factor = Math.pow(1.1, -Math.sign(event.deltaY));
    this._applyZoom(sx, sy, factor);
    // REQ-1.12: cancel pan if active
    if (this.isPanning) {
      this.isPanning = false;
    }
    this._wake();
  };

  Network.prototype._bindReducedMotion = function () {
    if (typeof window.matchMedia !== "function") return;
    this._reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    this._prefersReducedMotion = !!this._reducedMotionQuery.matches;
    var self = this;
    var onChange = function (event) {
      self._prefersReducedMotion = !!event.matches;
      self._wake();
    };
    if (typeof this._reducedMotionQuery.addEventListener === "function") {
      this._reducedMotionQuery.addEventListener("change", onChange);
    } else if (typeof this._reducedMotionQuery.addListener === "function") {
      this._reducedMotionQuery.addListener(onChange);
    }
  };

  Network.prototype._syncModesFromOptions = function (options) {
    var layout = options && options.layout && options.layout.hierarchical;
    var physics = options && options.physics;
    if (layout && typeof layout.enabled === "boolean") this.layoutMode = layout.enabled ? "hierarchical" : "free";
    if (physics && typeof physics.enabled === "boolean") this.physicsEnabled = physics.enabled;
  };

  Network.prototype.setOptions = function (options) {
    this.options = Object.assign({}, this.options, options || {});
    this._syncModesFromOptions(options || {});
    this._wake();
  };

  Network.prototype.setEdgeWidthScale = function (value) {
    var next = Number(value);
    if (!Number.isFinite(next) || next <= 0) next = 1;
    this._edgeWidthScale = next;
    this._wake();
  };

  Network.prototype.setLabelFontWeight = function (value) {
    var next = Number(value);
    if (!Number.isFinite(next) || next < 100) next = 400;
    this._labelFontWeight = next;
    this._wake();
  };

  Network.prototype.on = function (eventName, handler) {
    if (!this.handlers[eventName]) this.handlers[eventName] = [];
    this.handlers[eventName].push(handler);
  };

  Network.prototype.once = function (eventName, handler) {
    var self = this;
    var wrapper = function (payload) {
      handler(payload);
      var idx = (self.handlers[eventName] || []).indexOf(wrapper);
      if (idx >= 0) self.handlers[eventName].splice(idx, 1);
    };
    this.on(eventName, wrapper);
  };

  Network.prototype._emit = function (eventName, payload) {
    (this.handlers[eventName] || []).forEach(function (handler) { handler(payload || {}); });
  };

  // Slice 1b: focus accepts (nodeId, options) with scale and animation (REQ-1.10)
  Network.prototype.focus = function (nodeId, options) {
    var opts = options || {};
    this._selectNodeById(nodeId);
    var state = this._state();
    var node = state.nodes.find(function (n) { return String(n.id) === String(nodeId); });
    if (!node) return;
    // Apply scale if provided
    if (opts.scale !== undefined) {
      this.viewport.scale = opts.scale;
    }
    // Center viewport on the node
    this.viewport.tx = this.canvas.width / 2 - node.x * this.viewport.scale;
    this.viewport.ty = this.canvas.height / 2 - node.y * this.viewport.scale;
    // Animate if requested and motion allowed
    if (opts.animation && this.motionEnabled()) {
      this._animateViewport(
        { scale: this.viewport.scale, tx: this.viewport.tx, ty: this.viewport.ty },
        250
      );
    }
    this._wake();
  };

  // Slice 1b: fit re-implemented against viewport matrix (REQ-1.10) — MUST NOT set temperature=0.2
  Network.prototype.fit = function (options) {
    var opts = options || {};
    var state = this._state();
    var visibleNodes = state.nodes.filter(function (n) { return !n.hidden; });
    if (!visibleNodes.length) return;

    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    visibleNodes.forEach(function (n) {
      var r = n.radius || 8;
      if (n.x - r < minX) minX = n.x - r;
      if (n.y - r < minY) minY = n.y - r;
      if (n.x + r > maxX) maxX = n.x + r;
      if (n.y + r > maxY) maxY = n.y + r;
    });

    var margin = 40;
    var bboxW = maxX - minX;
    var bboxH = maxY - minY;
    if (bboxW <= 0 || bboxH <= 0) return;

    var scaleX = (this.canvas.width - margin * 2) / bboxW;
    var scaleY = (this.canvas.height - margin * 2) / bboxH;
    var newScale = Math.min(scaleX, scaleY);
    newScale = Math.max(0.25, Math.min(4.0, newScale));

    var centerX = (minX + maxX) / 2;
    var centerY = (minY + maxY) / 2;
    var newTx = this.canvas.width / 2 - centerX * newScale;
    var newTy = this.canvas.height / 2 - centerY * newScale;

    var target = { scale: newScale, tx: newTx, ty: newTy };

    if (opts.animation && this.motionEnabled()) {
      this._animateViewport(target, 250);
    } else {
      this.viewport.scale = newScale;
      this.viewport.tx = newTx;
      this.viewport.ty = newTy;
    }
    this._wake();
  };

  // Slice 1b: motionEnabled helper — single source of truth for all animated transitions (§4.3)
  Network.prototype.motionEnabled = function () {
    return !this._prefersReducedMotion;
  };

  // Slice 1b: animate viewport toward target over ms milliseconds (linear ease)
  Network.prototype._animateViewport = function (target, ms) {
    var self = this;
    var startScale = this.viewport.scale;
    var startTx = this.viewport.tx;
    var startTy = this.viewport.ty;
    var startTime = null;
    var duration = ms || 250;

    function step(ts) {
      if (!startTime) startTime = ts;
      var elapsed = ts - startTime;
      var t = Math.min(1, elapsed / duration);
      self.viewport.scale = startScale + (target.scale - startScale) * t;
      self.viewport.tx = startTx + (target.tx - startTx) * t;
      self.viewport.ty = startTy + (target.ty - startTy) * t;
      if (t < 1) {
        requestAnimationFrame(step);
      }
    }
    requestAnimationFrame(step);
  };

  // Slice 1a: reset viewport to identity — called on layout change (REQ-1.11)
  Network.prototype._resetViewport = function () {
    this.viewport = { scale: 1, tx: 0, ty: 0 };
    this._wake();
  };

  Network.prototype._state = function () {
    var nodes = (this.data.nodes && this.data.nodes.get()) || [];
    var edges = (this.data.edges && this.data.edges.get()) || [];
    this._ensureHierarchy(nodes);
    if (this._treeFilterRootId !== null && this._treeFilterDescendants && this._treeFilterDescendants.size > 0) {
      var idSet = this._treeFilterDescendants;
      nodes = nodes.filter(function (n) { return idSet.has(String(n.id)); });
      edges = edges.filter(function (e) {
        var fromId = String(e.from || e.source);
        var toId = String(e.to || e.target);
        return idSet.has(fromId) && idSet.has(toId);
      });
    }
    var i;
    for (i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.x === undefined || n.y === undefined) {
        n.x = (this.canvas.width / 2) + (Math.random() - 0.5) * 80;
        n.y = (this.canvas.height / 2) + (Math.random() - 0.5) * 80;
        n.vx = 0;
        n.vy = 0;
      }
      n.degree = 0;
    }
    edges.forEach(function (e) {
      var from = nodes.find(function (n) { return String(n.id) === String(e.from || e.source); });
      var to = nodes.find(function (n) { return String(n.id) === String(e.to || e.target); });
      if (from) from.degree += 1;
      if (to) to.degree += 1;
    });
    var neighborIndex = new Map();
    nodes.forEach(function (node) {
      neighborIndex.set(String(node.id), new Set());
    });
    edges.forEach(function (e) {
      var fromId = String(e.from || e.source);
      var toId = String(e.to || e.target);
      if (!neighborIndex.has(fromId)) neighborIndex.set(fromId, new Set());
      if (!neighborIndex.has(toId)) neighborIndex.set(toId, new Set());
      neighborIndex.get(fromId).add(toId);
      neighborIndex.get(toId).add(fromId);
    });
    this._neighborIndex = neighborIndex;
    return { nodes: nodes, edges: edges };
  };

  Network.prototype._ensureHierarchy = function (nodes) {
    if (this._hierarchyReady) return;
    var self = this;
    nodes.forEach(function (node) {
      var normalizedSupertype = String(node.supertype || node.type || "").toLowerCase();
      node.supertype = node.supertype || normalizedSupertype;
      node._parentId = (node.parent_id === undefined || node.parent_id === null) ? null : String(node.parent_id);
      node.hidden = false;
      if (node._parentId === null) {
        self.expandedNodeIds.add(String(node.id));
      }
    });
    this._hierarchyReady = true;
  };

  Network.prototype._computeDescendants = function (rootId) {
    var root = String(rootId);
    var nodes = (this.data.nodes && this.data.nodes.get()) || [];
    var childrenByParent = new Map();
    nodes.forEach(function (node) {
      if (!node) return;
      var parentId = (node.parent_id === undefined || node.parent_id === null) ? null : String(node.parent_id);
      if (parentId === null) return;
      if (!childrenByParent.has(parentId)) childrenByParent.set(parentId, []);
      childrenByParent.get(parentId).push(String(node.id));
    });
    var result = new Set([root]);
    var queue = [root];
    var visited = new Set([root]);
    while (queue.length > 0) {
      var current = queue.shift();
      var children = childrenByParent.get(current) || [];
      children.forEach(function (childId) {
        if (visited.has(childId)) return;
        visited.add(childId);
        result.add(childId);
        queue.push(childId);
      });
    }
    return result;
  };

  Network.prototype.setTreeFilter = function (rootId) {
    if (rootId === undefined || rootId === null) {
      this.clearTreeFilter();
      return;
    }
    this._treeFilterRootId = String(rootId);
    this._treeFilterDescendants = this._computeDescendants(rootId);
    this._wake();
  };

  Network.prototype.clearTreeFilter = function () {
    this._treeFilterRootId = null;
    this._treeFilterDescendants = null;
    this._wake();
  };

  // Slice 1a: reset viewport on expand/collapse (REQ-1.11)
  Network.prototype._toggleExpandCollapse = function (node, nodes) {
    if (!node) return;
    var id = String(node.id);
    var expanded = this.expandedNodeIds.has(id);
    if (expanded) {
      this.expandedNodeIds.delete(id);
    } else {
      this.expandedNodeIds.add(id);
    }
    var self = this;
    nodes.forEach(function (candidate) {
      if (!candidate) return;
      if (String(candidate.id) === id) return;
      if (String(candidate._parentId) !== id) return;
      var shouldShow = !expanded;
      candidate.hidden = !shouldShow;
      if (!expanded) {
        candidate.x = node.x;
        candidate.y = node.y;
      }
    });
    this.liveRegion.textContent = (expanded ? "Collapsed " : "Expanded ") + String(node.label || node.id);
    // Reset viewport on layout change (REQ-1.11)
    this._resetViewport();
  };

  Network.prototype._applyForces = function (state, dt) {
    var nodes = state.nodes;
    var edges = state.edges;
    var centerX = this.canvas.width / 2;
    var centerY = this.canvas.height / 2;
    var repulsion = 3600;
    var spring = 0.01;
    var restLength = 180;
    var gravity = 0.0024;
    var maxSteps = Math.min(500, nodes.length * nodes.length);
    var steps = 0;

    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      // Pin the node being dragged (and any node the user has dropped/fixed): it
      // keeps its position — driven by the drag handler — while still exerting
      // forces on its neighbors, so dragging one node visibly rearranges the rest
      // and the dropped node stays put instead of snapping back to the cluster.
      if (a.fixed || (this.dragNodeId !== null && String(a.id) === String(this.dragNodeId))) continue;
      var fx = 0;
      var fy = 0;

      for (var j = 0; j < nodes.length; j++) {
        if (i === j) continue;
        if (steps++ > maxSteps) break;
        var b = nodes[j];
        var dx = a.x - b.x;
        var dy = a.y - b.y;
        var distSq = (dx * dx + dy * dy) || 0.01;
        var dist = Math.sqrt(distSq);
        var force = repulsion * (1 / (dist * dist));
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      edges.forEach(function (edge) {
        var fromId = edge.from || edge.source;
        var toId = edge.to || edge.target;
        if (String(a.id) !== String(fromId) && String(a.id) !== String(toId)) return;
        var other = nodes.find(function (n) {
          return String(n.id) === String(String(a.id) === String(fromId) ? toId : fromId);
        });
        if (!other) return;
        var sx = other.x - a.x;
        var sy = other.y - a.y;
        var sl = Math.sqrt(sx * sx + sy * sy) || 0.01;
        var hooke = spring * (sl - restLength);
        fx += (sx / sl) * hooke;
        fy += (sy / sl) * hooke;
      });

      fx += (centerX - a.x) * gravity;
      fy += (centerY - a.y) * gravity;

      a.vx = (a.vx + fx * dt) * 0.92;
      a.vy = (a.vy + fy * dt) * 0.92;
      a.x += a.vx * this.temperature;
      a.y += a.vy * this.temperature;
    }
  };

  Network.prototype._drawEdges = function (state) {
    var ctx = this.ctx;
    var self = this;
    ctx.save();
    state.edges.forEach(function (edge) {
      var from = state.nodes.find(function (n) { return String(n.id) === String(edge.from || edge.source); });
      var to = state.nodes.find(function (n) { return String(n.id) === String(edge.to || edge.target); });
      if (!from || !to) return;
      var hoveredId = self.hoveredNodeId === null ? null : String(self.hoveredNodeId);
      var fromId = String(edge.from || edge.source);
      var toId = String(edge.to || edge.target);
      var isIncident = hoveredId !== null && (fromId === hoveredId || toId === hoveredId);
      if (hoveredId !== null && !isIncident) {
        ctx.globalAlpha = 0.15;
      } else {
        ctx.globalAlpha = 1;
      }
      ctx.beginPath();
      ctx.strokeStyle = isIncident
        ? (self._themeTokens.egoEdge || "#7c3aed")
        : ((edge.color && edge.color.color) || self._themeTokens.panelBorder || "#64748b");
      ctx.lineWidth = Math.max(0.25, Number(edge.width || edge.value || 1) * self._edgeWidthScale);
      var edgeDash = Math.max(1, Number(self._themeTokens.edgeDash || 6));
      ctx.setLineDash([edgeDash + 2, edgeDash]);
      if (self._prefersReducedMotion) {
        ctx.lineDashOffset = 0;
      } else {
        ctx.lineDashOffset = -self._dashOffset;
      }
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();

      var angle = Math.atan2(to.y - from.y, to.x - from.x);
      var arrow = Math.max(4, Number(self._themeTokens.edgeArrowheadSize || 8));
      ctx.beginPath();
      ctx.moveTo(to.x, to.y);
      ctx.lineTo(to.x - arrow * Math.cos(angle - 0.35), to.y - arrow * Math.sin(angle - 0.35));
      ctx.lineTo(to.x - arrow * Math.cos(angle + 0.35), to.y - arrow * Math.sin(angle + 0.35));
      ctx.closePath();
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
      ctx.globalAlpha = 1;
    });
    ctx.restore();
  };

  // Slice 3a: draw marquee rectangle between _drawEdges and _drawNodes (REQ-3.5)
  // Rendered in world coordinates; 1px on screen regardless of zoom (zoom-invariant)
  Network.prototype._drawMarquee = function () {
    if (!this.marquee.active) return;
    var ctx = this.ctx;
    ctx.save();
    var strokeColor = this._themeTokens.marqueeStroke || "#38bdf8";
    ctx.strokeStyle = strokeColor;
    ctx.fillStyle = this._themeTokens.marqueeFill || "rgba(56,189,248,0.12)";
    // Zoom-invariant 1px border: lineWidth = 1/scale (REQ-3.5)
    ctx.lineWidth = 1 / this.viewport.scale;
    ctx.setLineDash([4 / this.viewport.scale, 4 / this.viewport.scale]);
    var x = this.marquee.x0;
    var y = this.marquee.y0;
    var w = this.marquee.x1 - this.marquee.x0;
    var h = this.marquee.y1 - this.marquee.y0;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    ctx.restore();
  };

  Network.prototype._drawNodes = function (state) {
    var ctx = this.ctx;
    var self = this;
    ctx.save();
    var hoveredId = self.hoveredNodeId === null ? null : String(self.hoveredNodeId);
    var hoveredNeighborhood = hoveredId !== null
      ? (self._neighborIndex.get(hoveredId) || new Set())
      : null;
    state.nodes.forEach(function (node) {
      if (node.hidden) return;
      if (hoveredId !== null) {
        var isNeighbor = hoveredNeighborhood && hoveredNeighborhood.has(String(node.id));
        var keepFull = String(node.id) === hoveredId || isNeighbor;
        ctx.globalAlpha = keepFull ? 1 : 0.15;
      } else {
        ctx.globalAlpha = 1;
      }
      var degree = node.degree || 0;
      var importance = Number(node.importance || node.score || degree || 1);
      var isRoot = !!node.is_root || String(node.supertype || "").toLowerCase().indexOf("org") >= 0;
      var radiusBase = Math.max(8, degree * 2 + 8);
      var radius = Math.max(12, radiusBase + Math.min(10, Math.max(0, importance)));
      if (isRoot) radius = radius + 8;
      node.radius = radius;
      ctx.beginPath();
      ctx.fillStyle = self._resolveNodeBackground(node);
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();
      var nodeTypeColor = self._themeTokens.entityFillByType[String(node.type || "")];
      if (nodeTypeColor) {
        ctx.save();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = nodeTypeColor;
        ctx.stroke();
        ctx.restore();
      }
      var activeTheme = self._activeThemeName();
      var fallbackByTheme = self._themeTokens.outlineFallbackByTheme || {};
      var outlineTypes = fallbackByTheme[activeTheme] || {};
      if (outlineTypes[String(node.type || "")]) {
        ctx.save();
        ctx.lineWidth = 1;
        ctx.strokeStyle = self._themeTokens.popoverMuted || "#cbd5e1";
        ctx.stroke();
        ctx.restore();
      }
      if (String(node.id) === String(self.hoveredNodeId)) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = self._themeTokens.popoverMuted || "#f59e0b";
        ctx.stroke();
      }
      if (String(node.id) === String(self.selectedNodeId)) {
        ctx.lineWidth = Math.min(8, 2 / self.viewport.scale);
        ctx.strokeStyle = self._themeTokens.focusRing || "#38bdf8";
        ctx.stroke();
      }
      if (String(node.id) === String(self.keyboardFocusedNodeId)) {
        ctx.save();
        ctx.lineWidth = Math.min(6, 1.5 / self.viewport.scale);
        ctx.strokeStyle = self._themeTokens.stateFocusRing || self._themeTokens.focusRing || "#38bdf8";
        ctx.setLineDash([4 / self.viewport.scale, 4 / self.viewport.scale]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
      ctx.fillStyle = self._themeTokens.panelText || "#f5f6f7";
      ctx.font = String(self._labelFontWeight) + " 12px sans-serif";
      ctx.fillText(String(node.label || node.id), node.x + radius + 4, node.y + 4);
      ctx.globalAlpha = 1;
    });
    ctx.restore();
  };

  Network.prototype._syncA11yList = function (nodes) {
    this.a11yList.innerHTML = "";
    var self = this;
    var visibleNodes = [];
    nodes.forEach(function (node) {
      if (node.hidden) return;
      visibleNodes.push(node);
      var li = document.createElement("li");
      li.id = "vis-a11y-node-" + String(node.id);
      li.className = "vis-a11y-option";
      li.setAttribute("role", "option");
      li.setAttribute("tabindex", "0");
      li.setAttribute("aria-selected", String(String(node.id) === String(self.selectedNodeId)));
      // Slice 4: link each node's a11y element to the shared popover (REQ-4.10)
      li.setAttribute("aria-describedby", "vis-hover-popover");
      li.textContent = String(node.label || node.id);
      li.addEventListener("click", function () {
        self._selectNodeById(node.id);
      });
      li.addEventListener("keydown", function (event) {
        self._onA11yKeydown(event, visibleNodes);
      });
      // Slice 4: Tab focus on a node shows popover immediately, no delay (REQ-4.8)
      li.addEventListener("focus", (function (capturedNode) {
        return function () {
          self.keyboardFocusedNodeId = capturedNode.id;
          self._showHoverPopover(capturedNode.id, capturedNode.x, capturedNode.y);
          self._wake();
        };
      })(node));
      li.addEventListener("blur", function () {
        self.keyboardFocusedNodeId = null;
        self._wake();
        // On blur start grace timer so popover dismisses after short delay (REQ-4.2 / REQ-4.8)
        clearTimeout(self._popoverGraceTimer);
        self._popoverGraceTimer = setTimeout(function () {
          self._popoverGraceTimer = null;
          self._hideHoverPopover();
        }, 150);
      });
      self.a11yList.appendChild(li);
    });

    this.a11yList.setAttribute("aria-activedescendant", "");
    if (!visibleNodes.length) {
      this._activeA11yIndex = -1;
      return;
    }
    var currentIndex = visibleNodes.findIndex(function (node) {
      return String(node.id) === String(self.selectedNodeId);
    });
    this._activeA11yIndex = currentIndex >= 0 ? currentIndex : 0;
    var activeNode = visibleNodes[this._activeA11yIndex];
    this.a11yList.setAttribute("aria-activedescendant", "vis-a11y-node-" + String(activeNode.id));
  };

  Network.prototype._selectNodeById = function (nodeId) {
    this.selectedNodeId = nodeId;
    this.liveRegion.textContent = "Selected " + String(nodeId);
    this._emit("click", { nodes: [nodeId] });
    this._wake();
  };

  Network.prototype._moveA11yFocus = function (delta, nodes) {
    if (!nodes.length) return;
    var next = this._activeA11yIndex + delta;
    if (next < 0) next = nodes.length - 1;
    if (next >= nodes.length) next = 0;
    this._activeA11yIndex = next;
    var node = nodes[this._activeA11yIndex];
    var id = "vis-a11y-node-" + String(node.id);
    this.a11yList.setAttribute("aria-activedescendant", id);
    var item = document.getElementById(id);
    if (item && typeof item.focus === "function") item.focus();
  };

  Network.prototype._onA11yKeydown = function (event, nodes) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      this._moveA11yFocus(1, nodes);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      this._moveA11yFocus(-1, nodes);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      var active = nodes[this._activeA11yIndex];
      if (active) this._selectNodeById(active.id);
    }
  };

  Network.prototype._onCanvasKeydown = function (event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
    }

    // Slice 3a: Escape — clear selection (REQ-3.9)
    // Slice 4: Esc also dismisses popover without clearing node focus (REQ-4.8 / OBS-4.11)
    if (event.key === "Escape") {
      event.preventDefault();
      if (this._treeFilterRootId !== null) {
        this.clearTreeFilter();
        return;
      }
      // Dismiss popover first; if popover was shown, keep focus on node (OBS-4.11)
      if (this._popoverNodeId !== null) {
        this._hideHoverPopover();
        return;  // Esc on open popover = dismiss only; selection stays
      }
      this.selectedNodeIds = new Set();
      this.selectedNodeId = null;
      this.marquee.active = false;
      this._mode = "idle";
      this._emit("select-change", { nodes: [] });
      this.liveRegion.textContent = "Selection cleared";
      this._wake();
      return;
    }

    // Slice 3a: Ctrl/Cmd+A — select all visible nodes (REQ-3.8)
    if ((event.ctrlKey || event.metaKey) && event.key === "a") {
      event.preventDefault();
      var state = this._state();
      var visibleIds = [];
      state.nodes.forEach(function (n) {
        if (!n.hidden) visibleIds.push(String(n.id));
      });
      this.selectedNodeIds = new Set(visibleIds);
      this.selectedNodeId = visibleIds.length > 0 ? visibleIds[visibleIds.length - 1] : null;
      this._emit("select-change", { nodes: visibleIds });
      this.liveRegion.textContent = this.selectedNodeIds.size + " nodes selected";
      this._wake();
      return;
    }

    // TODO REQ-3.7: Shift+Arrow directional extend (deferred — no spatial neighbor index yet)
    // When implemented: extend selection by selecting the neighbor of the most-recently-selected
    // node in the direction closest to the arrow direction (angular distance heuristic).
  };

  Network.prototype._nodeAt = function (x, y, nodes) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var dx = x - n.x;
      var dy = y - n.y;
      if ((dx * dx + dy * dy) <= ((n.radius || 8) * (n.radius || 8))) return n;
    }
    return null;
  };

  // Slice 1a: all event handlers use _screenToWorld before _nodeAt (REQ-1.9 / OBS-1.8)

  Network.prototype._onClick = function (event) {
    // Slice 3a: suppress the click that fires after a marquee mouseup (REQ-3.5)
    if (this._suppressNextClick) { this._suppressNextClick = false; return; }
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    // Slice 1a: inverse transform before hit-testing
    var world = this._screenToWorld(sx, sy);
    var state = this._state();
    var node = this._nodeAt(world.x, world.y, state.nodes);
    if (!node) {
      this.selectedNodeId = null;
      // Slice 3a: clear multi-select on empty-canvas click (REQ-3.1 / REQ-3.9 semantics)
      this.selectedNodeIds = new Set();
      this._emit("click", { nodes: [] });
      this._emit("select-change", { nodes: [] });
      this.liveRegion.textContent = "Selection cleared";
      this._wake();
      return;
    }
    this._toggleExpandCollapse(node, state.nodes);
    var nodeId = String(node.id);

    // Slice 3a: modifier-key selection semantics (REQ-3.1, 3.2, 3.3)
    if (event.ctrlKey || event.metaKey) {
      // Ctrl/Cmd-click: ADD to selection without removing (REQ-3.3)
      this.selectedNodeIds.add(nodeId);
    } else if (event.shiftKey) {
      // Shift-click: TOGGLE in/out of selection (REQ-3.2)
      if (this.selectedNodeIds.has(nodeId)) {
        this.selectedNodeIds.delete(nodeId);
      } else {
        this.selectedNodeIds.add(nodeId);
      }
    } else {
      // No modifier: REPLACE selection with only this node (REQ-3.1)
      this.selectedNodeIds = new Set([nodeId]);
    }

    // Keep legacy selectedNodeId in sync — last-selected primary node
    this.selectedNodeId = node.id;
    var count = this.selectedNodeIds.size;
    this.liveRegion.textContent = count === 1
      ? "Selected " + String(node.label || node.id)
      : count + " nodes selected";
    this._emit("click", { nodes: [node.id] });
    this._emit("select-change", { nodes: Array.from(this.selectedNodeIds) });
    this._wake();
  };

  Network.prototype._onMouseMove = function (event) {
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    // Slice 1a: inverse transform before hit-testing
    var world = this._screenToWorld(sx, sy);
    var state = this._state();
    var node = this._nodeAt(world.x, world.y, state.nodes);
    var prevHoveredId = this.hoveredNodeId;
    this.hoveredNodeId = node ? node.id : null;

    // Slice 4: manage hover-delay timer (REQ-4.1 / OBS-4.1).
    // Fire timer when cursor enters a new node; cancel and hide on node leave.
    // Suppress during active marquee, pan drag, node drag, or open context menu
    // (REQ-4.6 / REQ-6.10 — contextMenu.open gate added in Slice 6).
    if (!this.marquee.active && !this.isDragging && !this.isPanning && !(this.contextMenu && this.contextMenu.open)) {
      if (this.hoveredNodeId !== prevHoveredId) {
        // Node changed — cancel any pending show
        clearTimeout(this._popoverTimer);
        this._popoverTimer = null;
        if (this.hoveredNodeId !== null) {
          // Cursor moved to a new node — cancel grace timer if any, arm show timer
          clearTimeout(this._popoverGraceTimer);
          this._popoverGraceTimer = null;
          if (this._popoverNodeId !== null) {
            this._hideHoverPopover();
          }
          var self = this;
          var targetId = this.hoveredNodeId;
          this._popoverTimer = setTimeout(function () {
            // Re-check hover is still on same node (REQ-4.1 — delay must elapse)
            if (String(self.hoveredNodeId) === String(targetId)) {
              self._showHoverPopover(targetId, world.x, world.y);
            }
          }, this.hoverDelayMs);
        } else {
          // Cursor left a node — REQ-4.2: 150 ms grace before hiding
          // If cursor re-enters within 150 ms, the grace timer is cancelled above
          var self = this;
          this._popoverGraceTimer = setTimeout(function () {
            self._popoverGraceTimer = null;
            self._hideHoverPopover();
          }, 150);
        }
      }
    }

    if (this.isPanning) {
      // Slice 1a: pan — update tx/ty from screen delta (REQ-1.2 / OBS-1.1)
      this.viewport.tx = this.panStart.tx0 + (sx - this.panStart.x);
      this.viewport.ty = this.panStart.ty0 + (sy - this.panStart.y);
      // Slice 1b: track last velocity sample for inertia handoff (REQ-1.7)
      var now = Date.now();
      this.panStart.lastDx = sx - this.panStart.lastSx;
      this.panStart.lastDy = sy - this.panStart.lastSy;
      this.panStart.lastT = now;
      this.panStart.lastSx = sx;
      this.panStart.lastSy = sy;
      this._wake();
      return;
    }

    // Slice 3a: marquee update — track far corner in world coords (REQ-3.5)
    if (this.marquee.active) {
      this.marquee.x1 = world.x;
      this.marquee.y1 = world.y;
      this._wake();
      return;
    }

    if (this.isDragging && this.dragNodeId !== null) {
      var dragged = state.nodes.find(function (n) { return String(n.id) === String(this.dragNodeId); }, this);
      if (dragged) {
        // Slice 1a: use world coords for drag position (not raw screen)
        dragged.x = world.x;
        dragged.y = world.y;
        dragged.vx = 0;
        dragged.vy = 0;
        this.temperature = Math.max(this.temperature, 0.2);
      }
    }
    this._wake();
  };

  Network.prototype._onMouseDown = function (event) {
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    // Slice 1a: inverse transform before hit-testing (REQ-1.9)
    var world = this._screenToWorld(sx, sy);
    var state = this._state();
    var node = this._nodeAt(world.x, world.y, state.nodes);
    if (node) {
      // Node drag takes priority — NOT panning (OBS-1.2)
      this.isDragging = true;
      this.dragNodeId = node.id;
      this._mode = "dragging-node";
      return;
    }
    // Slice 3a: Shift+empty canvas → marquee (REQ-3.5 / REQ-3.13)
    // MUST short-circuit BEFORE pan so isPanning and marquee.active are never both true
    if (event.shiftKey) {
      this.marquee = { active: true, x0: world.x, y0: world.y, x1: world.x, y1: world.y };
      this._mode = "marquee";
      return;
    }
    // Slice 4: dismiss popover when pan begins (REQ-4.6)
    this._hideHoverPopover();
    // No node hit, no shift: start panning (REQ-1.2)
    // Slice 1b: REQ-1.13 — zero inertia velocity when new pan drag begins
    this.viewport.vx = 0;
    this.viewport.vy = 0;
    this.inertiaActive = false;
    this.isPanning = true;
    this._mode = "panning";
    var now = Date.now();
    this.panStart = {
      x: sx, y: sy,
      tx0: this.viewport.tx, ty0: this.viewport.ty,
      lastDx: 0, lastDy: 0, lastT: now,
      lastSx: sx, lastSy: sy
    };
  };

  Network.prototype._onMouseUp = function () {
    this.isDragging = false;
    this.dragNodeId = null;
    this._mode = "idle";

    // Slice 3a: marquee commit — REPLACE selection (Decision 2 / REQ-3.6)
    if (this.marquee.active) {
      var left   = Math.min(this.marquee.x0, this.marquee.x1);
      var right  = Math.max(this.marquee.x0, this.marquee.x1);
      var top    = Math.min(this.marquee.y0, this.marquee.y1);
      var bottom = Math.max(this.marquee.y0, this.marquee.y1);
      var state = this._state();
      var enclosedIds = [];
      state.nodes.forEach(function (n) {
        if (n.hidden) return;
        // Enclose-only: node center must be fully inside marquee rect (REQ-3.6)
        if (n.x >= left && n.x <= right && n.y >= top && n.y <= bottom) {
          enclosedIds.push(String(n.id));
        }
      });
      // REPLACE selection — not additive (Decision 2)
      this.selectedNodeIds = new Set(enclosedIds);
      this.selectedNodeId = enclosedIds.length > 0 ? enclosedIds[enclosedIds.length - 1] : null;
      this._emit("select-change", { nodes: enclosedIds });
      var marqueeCount = this.selectedNodeIds.size;
      this.liveRegion.textContent = marqueeCount + " nodes selected by marquee";
      this.marquee.active = false;
      // Slice 3a: suppress the browser click event that follows this mouseup (REQ-3.5)
      this._suppressNextClick = true;
      this._wake();
      return;
    }

    // Slice 1b: compute pan velocity and arm inertia (REQ-1.7)
    if (this.isPanning) {
      var dt = Math.max(Date.now() - this.panStart.lastT, 16);
      var vx = this.panStart.lastDx / dt;
      var vy = this.panStart.lastDy / dt;
      this.viewport.vx = vx;
      this.viewport.vy = vy;
      // Arm inertia if velocity is significant (REQ-1.7)
      this.inertiaActive = (Math.abs(vx) + Math.abs(vy)) > this.minPanVelocity;
      if (this.inertiaActive) {
        this._wake();
      }
    }
    this.isPanning = false;
  };

  // Slice 1b: inertia integrator — Euler step with friction (REQ-1.7, REQ-1.8)
  Network.prototype._stepInertia = function (dt) {
    if (!this.inertiaActive || this._prefersReducedMotion) return;
    // Euler step: translate by velocity * elapsed (vx/vy are px/ms, dt is seconds)
    this.viewport.tx += this.viewport.vx * dt * 1000;
    this.viewport.ty += this.viewport.vy * dt * 1000;
    // Apply friction per frame
    this.viewport.vx *= this.inertiaFriction;
    this.viewport.vy *= this.inertiaFriction;
    // Stop when velocity falls below threshold (0.05 world-units — using px/ms threshold)
    if ((Math.abs(this.viewport.vx) + Math.abs(this.viewport.vy)) < this.minPanVelocity) {
      this.inertiaActive = false;
      this.viewport.vx = 0;
      this.viewport.vy = 0;
    }
  };

  Network.prototype._render = function (ts) {
    var dt = this._lastTs ? Math.min(0.033, (ts - this._lastTs) / 1000) : 0.016;
    this._lastTs = ts;
    var state = this._state();

    if (!this._prefersReducedMotion && this.physicsEnabled && this.temperature >= 0.01) {
      this._applyForces(state, dt);
      this.temperature = this.temperature * 0.95;
    }

    if (this._prefersReducedMotion) {
      this._dashOffset = 0;
    } else {
      this._dashOffset += dt * 40;
    }

    // Slice 1a: clear under identity, then apply viewport transform (REQ-1.1)
    var ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);  // identity for clearRect
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    ctx.save();
    ctx.setTransform(
      this.viewport.scale, 0,
      0, this.viewport.scale,
      this.viewport.tx, this.viewport.ty
    );
    if (!this._d4OverlayActive) {
      this._drawEdges(state);
      this._drawMarquee();  // Slice 3a: between edges and nodes (REQ-3.5)
      this._drawNodes(state);
    }
    ctx.restore();

    if (!this._d4OverlayActive) {
      this._syncA11yList(state.nodes);
    }

    // Slice 4: update popover screen position each frame (REQ-4.4 — tracks node's screen pos)
    this._updatePopoverPosition(state.nodes);

    // Slice 1b: inertia step after draw (REQ-1.7)
    this._stepInertia(dt);

    // Emit afterDrawing after each render frame so consumers can hook
    // the first paint (e.g. dismiss loading state). Uses once() for single-fire.
    this._frameCount++;
    this._emit("afterDrawing", { frameCount: this._frameCount });

    // Slice 1b: keep RAF alive while inertia is active (REQ-1.7 / 1b.12)
    // Slice 3a: also keep alive while marquee is being drawn
    var needsFrame = (
      (!this._prefersReducedMotion && this.physicsEnabled && this.temperature >= 0.01) ||
      this.inertiaActive ||
      this.marquee.active
    );
    if (needsFrame) {
      this._raf = requestAnimationFrame(this._render.bind(this));
    } else {
      this._raf = null;
    }
  };

  // Slice 4: show hover popover with node metadata (REQ-4.3 / REQ-4.4 / OBS-4.2).
  // Content factory pattern: template calls network.setPopoverContentFactory(fn) to
  // supply richer content; renderer falls back to a compact default. (design §3 Slice 4)
  Network.prototype._showHoverPopover = function (nodeId, wx, wy) {
    var state = this._state();
    var node = state.nodes.find(function (n) { return String(n.id) === String(nodeId); });
    if (!node) return;

    // Build popover content — lead with name, then type, then score, then source (cognitive-doc-design)
    var lines = [];
    if (node.label) lines.push('<strong class="vis-popover-name">' + String(node.label) + '</strong>');
    if (node.type || node.group) {
      lines.push('<span class="vis-popover-type">' + String(node.type || node.group) + '</span>');
    }
    if (node.score !== undefined && node.score !== null) {
      lines.push('<span class="vis-popover-score">Score: ' + Number(node.score).toFixed(2) + '</span>');
    }
    if (node.source) {
      lines.push('<span class="vis-popover-source">Source: ' + String(node.source) + '</span>');
    }

    // Use content factory if registered, otherwise default HTML (design §3 Slice 4)
    if (this._popoverContentFactory) {
      this._popoverEl.innerHTML = '';
      var child = this._popoverContentFactory(nodeId);
      if (child) this._popoverEl.appendChild(child);
    } else {
      this._popoverEl.innerHTML = lines.join('');
    }

    this._popoverNodeId = nodeId;
    // Honor prefers-reduced-motion: no fade animation (REQ-4.7 / REQ-X.2)
    if (this._prefersReducedMotion) {
      this._popoverEl.classList.add('vis-popover--instant');
    } else {
      this._popoverEl.classList.remove('vis-popover--instant');
    }
    this._popoverEl.setAttribute('aria-hidden', 'false');
    this._popoverEl.style.display = 'block';
    this._popoverEl.style.visibility = 'visible';

    // Position immediately (will also be updated each frame)
    this._updatePopoverPosition(state.nodes);
  };

  // Slice 4: hide and clear popover (REQ-4.6 / OBS-4.5 / OBS-4.6 / OBS-4.7).
  // Always cancels the pending timer too (REQ-4.6 — suppress pending show).
  Network.prototype._hideHoverPopover = function () {
    clearTimeout(this._popoverTimer);
    this._popoverTimer = null;
    clearTimeout(this._popoverGraceTimer);
    this._popoverGraceTimer = null;
    this._popoverNodeId = null;
    this._popoverEl.setAttribute('aria-hidden', 'true');
    this._popoverEl.style.display = 'none';
    this._popoverEl.style.visibility = 'hidden';
  };

  // Slice 4: reposition popover so it tracks the node's current screen position each frame.
  // Uses _worldToScreen (REQ-4.4) and clamps to canvas bounding box (REQ-4.5 / OBS-4.8).
  // Design decision: inject into .vis-network container (position relative), not body.
  Network.prototype._updatePopoverPosition = function (nodes) {
    if (!this._popoverNodeId || this._popoverEl.style.display === 'none') return;
    var node = (nodes || []).find(function (n) { return String(n.id) === String(this._popoverNodeId); }, this);
    if (!node) return;

    var screen = this._worldToScreen(node.x, node.y);
    var nodeR = node.radius || 12;  // fallback radius if not computed yet

    // Default anchor: above-right of node circle (+offset)
    var LEFT_OFFSET = 8;
    var TOP_OFFSET = -8;
    var rawLeft = screen.x + nodeR + LEFT_OFFSET;
    var rawTop  = screen.y + TOP_OFFSET;

    // Clamp to canvas bounding box (REQ-4.5). Flip all four edges independently.
    var pw = this._popoverEl.offsetWidth  || 160;
    var ph = this._popoverEl.offsetHeight || 64;
    var cw = this.canvas.width;
    var ch = this.canvas.height;

    // Horizontal flip: overflow right → flip to left of node
    if (rawLeft + pw > cw) {
      rawLeft = screen.x - nodeR - LEFT_OFFSET - pw;
    }
    // Vertical flip: overflow top → flip below node
    if (rawTop < 0) {
      rawTop = screen.y + nodeR + 4;
    }
    // Clamp bottom overflow
    if (rawTop + ph > ch) {
      rawTop = ch - ph - 4;
    }
    // Clamp left overflow
    if (rawLeft < 0) {
      rawLeft = 4;
    }

    this._popoverEl.style.left = rawLeft + 'px';
    this._popoverEl.style.top  = rawTop  + 'px';
  };

  // Slice 4: register a content factory function for richer popover content (design §3 Slice 4).
  // Template calls: network.setPopoverContentFactory((nodeId) => HTMLElement)
  Network.prototype.setPopoverContentFactory = function (factory) {
    this._popoverContentFactory = factory;
  };

  // Slice 3a: clearSelection — callable from template bulk actions (design §3 Slice 3)
  Network.prototype.clearSelection = function () {
    this.selectedNodeIds = new Set();
    this.selectedNodeId = null;
    this._emit("select-change", { nodes: [] });
    this.liveRegion.textContent = "Selection cleared";
    this._wake();
  };

  // vis compatibility: template/runtime may call selectNodes([id]) directly.
  Network.prototype.selectNodes = function (ids) {
    var selectedIds = Array.isArray(ids) ? ids : [];
    if (!selectedIds.length) {
      this.clearSelection();
      return;
    }
    this.selectedNodeIds = new Set(selectedIds.map(function (id) { return String(id); }));
    this._selectNodeById(selectedIds[0]);
    this._emit("select-change", { nodes: Array.from(this.selectedNodeIds) });
  };

  // Slice 6: contextmenu handler — suppress browser default, hit-test for node,
  // hide active popover (REQ-6.10 / OBS-6.11), emit 'context-menu' event (REQ-6.1 / REQ-6.2).
  Network.prototype._onContextMenu = function (event) {
    event.preventDefault();
    // REQ-6.10 / OBS-6.11: dismiss any active hover popover when context menu opens.
    this._hideHoverPopover();
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    var world = this._screenToWorld(sx, sy);
    var state = this._state();
    var node = this._nodeAt(world.x, world.y, state.nodes);
    // Update contextMenu state so _onMouseMove hover-suppression gate works (REQ-6.10).
    this.contextMenu.open = true;
    this.contextMenu.x = sx;
    this.contextMenu.y = sy;
    this.contextMenu.target = node ? String(node.id) : null;
    this._emit("context-menu", {
      nodeId: node ? String(node.id) : null,
      screen: { x: event.clientX, y: event.clientY },
      world: { x: world.x, y: world.y },
      selection: Array.from(this.selectedNodeIds),
    });
  };

  // Slice 6: close the context menu — called by template on Esc / click-outside / item select.
  Network.prototype.closeContextMenu = function () {
    this.contextMenu.open = false;
    this.contextMenu.target = null;
  };

  Network.prototype._wake = function () {
    if (this.temperature < 0.01) this.temperature = 0.25;
    if (this._raf) return;
    this._raf = requestAnimationFrame(this._render.bind(this));
  };

  window.vis = { Network: Network, DataSet: DataSet };
})();
