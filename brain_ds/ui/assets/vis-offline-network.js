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

    // Slice 1a: viewport matrix (REQ-1.1)
    this.viewport = { scale: 1, tx: 0, ty: 0 };

    // Slice 1a: pan state — DISTINCT from isDragging/dragNodeId (REQ-1.2)
    this.isPanning = false;
    this.panStart = { x: 0, y: 0, tx0: 0, ty0: 0 };

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

    var rerender = this._wake.bind(this);
    if (this.data.nodes && this.data.nodes._subscribe) this.data.nodes._subscribe(rerender);
    if (this.data.edges && this.data.edges._subscribe) this.data.edges._subscribe(rerender);

    this.canvas.addEventListener("click", this._onClick.bind(this));
    this.canvas.addEventListener("mousemove", this._onMouseMove.bind(this));
    this.canvas.addEventListener("mousedown", this._onMouseDown.bind(this));
    this.canvas.addEventListener("mouseup", this._onMouseUp.bind(this));
    this.canvas.addEventListener("keydown", this._onCanvasKeydown.bind(this));
    this._bindReducedMotion();
    this._syncModesFromOptions(this.options);
    this._wake();
  }

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

  Network.prototype.on = function (eventName, handler) {
    if (!this.handlers[eventName]) this.handlers[eventName] = [];
    this.handlers[eventName].push(handler);
  };

  Network.prototype._emit = function (eventName, payload) {
    (this.handlers[eventName] || []).forEach(function (handler) { handler(payload || {}); });
  };

  Network.prototype.focus = function (nodeId) {
    this._selectNodeById(nodeId);
  };

  Network.prototype.fit = function () {
    this.temperature = 0.2;
    this._wake();
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
    return { nodes: nodes, edges: edges };
  };

  Network.prototype._ensureHierarchy = function (nodes) {
    if (this._hierarchyReady) return;
    var root = this._findRootNode(nodes);
    if (!root) {
      this._hierarchyReady = true;
      return;
    }
    this.expandedNodeIds.add(String(root.id));
    var self = this;
    nodes.forEach(function (node) {
      var normalizedSupertype = String(node.supertype || node.type || "").toLowerCase();
      node.supertype = node.supertype || normalizedSupertype;
      node._parentId = self._inferParentId(node, root.id);
      if (String(node.id) === String(root.id)) {
        node.hidden = false;
        return;
      }
      node.hidden = String(node._parentId) !== String(root.id);
    });
    this._hierarchyReady = true;
  };

  Network.prototype._findRootNode = function (nodes) {
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i] && nodes[i].is_root) return nodes[i];
    }
    for (var j = 0; j < nodes.length; j++) {
      var n = nodes[j];
      var supertype = String((n && (n.supertype || n.type)) || "").toLowerCase();
      if (supertype.indexOf("organization") >= 0 || supertype.indexOf("org") >= 0) {
        n.is_root = true;
        return n;
      }
    }
    return nodes.length ? nodes[0] : null;
  };

  Network.prototype._inferParentId = function (node, rootId) {
    if (!node) return rootId;
    if (node.parent !== undefined && node.parent !== null) return node.parent;
    if (node.parent_id !== undefined && node.parent_id !== null) return node.parent_id;
    var supertype = String(node.supertype || node.type || "").toLowerCase();
    if (supertype.indexOf("department") >= 0 || supertype.indexOf("actor") >= 0 || supertype.indexOf("data") >= 0 || supertype.indexOf("process") >= 0) {
      return rootId;
    }
    return rootId;
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
    var repulsion = 2400;
    var spring = 0.01;
    var restLength = 120;
    var gravity = 0.003;
    var maxSteps = Math.min(500, nodes.length * nodes.length);
    var steps = 0;

    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
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
      ctx.beginPath();
      ctx.strokeStyle = (edge.color && edge.color.color) || "#64748b";
      ctx.lineWidth = Math.max(1, Number(edge.width || edge.value || 1));
      ctx.setLineDash([8, 6]);
      if (self._prefersReducedMotion) {
        ctx.lineDashOffset = 0;
      } else {
        ctx.lineDashOffset = -self._dashOffset;
      }
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();

      var angle = Math.atan2(to.y - from.y, to.x - from.x);
      var arrow = 8;
      ctx.beginPath();
      ctx.moveTo(to.x, to.y);
      ctx.lineTo(to.x - arrow * Math.cos(angle - 0.35), to.y - arrow * Math.sin(angle - 0.35));
      ctx.lineTo(to.x - arrow * Math.cos(angle + 0.35), to.y - arrow * Math.sin(angle + 0.35));
      ctx.closePath();
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
    });
    ctx.restore();
  };

  Network.prototype._drawNodes = function (state) {
    var ctx = this.ctx;
    var self = this;
    ctx.save();
    state.nodes.forEach(function (node) {
      if (node.hidden) return;
      var degree = node.degree || 0;
      var importance = Number(node.importance || node.score || degree || 1);
      var isRoot = !!node.is_root || String(node.supertype || "").toLowerCase().indexOf("org") >= 0;
      var radiusBase = Math.max(8, degree * 2 + 8);
      var radius = Math.max(12, radiusBase + Math.min(10, Math.max(0, importance)));
      if (isRoot) radius = radius + 8;
      node.radius = radius;
      ctx.beginPath();
      ctx.fillStyle = (node.color && node.color.background) || "#1e293b";
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();
      if (String(node.id) === String(self.hoveredNodeId)) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#f59e0b";
        ctx.stroke();
      }
      if (String(node.id) === String(self.selectedNodeId)) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#38bdf8";
        ctx.stroke();
      }
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "12px sans-serif";
      ctx.fillText(String(node.label || node.id), node.x + radius + 4, node.y + 4);
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
      li.textContent = String(node.label || node.id);
      li.addEventListener("click", function () {
        self._selectNodeById(node.id);
      });
      li.addEventListener("keydown", function (event) {
        self._onA11yKeydown(event, visibleNodes);
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
    var rect = this.canvas.getBoundingClientRect();
    var sx = event.clientX - rect.left;
    var sy = event.clientY - rect.top;
    // Slice 1a: inverse transform before hit-testing
    var world = this._screenToWorld(sx, sy);
    var state = this._state();
    var node = this._nodeAt(world.x, world.y, state.nodes);
    if (!node) {
      this.selectedNodeId = null;
      this._emit("click", { nodes: [] });
      this._wake();
      return;
    }
    this._toggleExpandCollapse(node, state.nodes);
    this.selectedNodeId = node.id;
    this.liveRegion.textContent = "Selected " + String(node.label || node.id);
    this._emit("click", { nodes: [node.id] });
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
    this.hoveredNodeId = node ? node.id : null;

    if (this.isPanning) {
      // Slice 1a: pan — update tx/ty from screen delta (REQ-1.2 / OBS-1.1)
      this.viewport.tx = this.panStart.tx0 + (sx - this.panStart.x);
      this.viewport.ty = this.panStart.ty0 + (sy - this.panStart.y);
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
      return;
    }
    // No node hit: start panning (REQ-1.2)
    this.isPanning = true;
    this.panStart = { x: sx, y: sy, tx0: this.viewport.tx, ty0: this.viewport.ty };
  };

  Network.prototype._onMouseUp = function () {
    this.isDragging = false;
    this.dragNodeId = null;
    // Slice 1a: clear pan state (leave TODO for 1b velocity stash)
    this.isPanning = false;
    // TODO(1b): stash final pan velocity for inertia handoff
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
    this._drawEdges(state);
    this._drawNodes(state);
    ctx.restore();

    this._syncA11yList(state.nodes);

    if (!this._prefersReducedMotion && this.physicsEnabled && this.temperature >= 0.01) {
      this._raf = requestAnimationFrame(this._render.bind(this));
    } else {
      this._raf = null;
    }
  };

  Network.prototype._wake = function () {
    if (this.temperature < 0.01) this.temperature = 0.25;
    if (this._raf) return;
    this._raf = requestAnimationFrame(this._render.bind(this));
  };

  window.vis = { Network: Network, DataSet: DataSet };
})();
