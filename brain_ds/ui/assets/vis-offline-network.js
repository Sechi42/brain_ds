/* brain_ds offline vis fallback exposing window.vis with deterministic controls */
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
    this.layoutMode = "hierarchical";
    this.physicsEnabled = false;
    this.selectedNodeId = null;

    this.container.classList.add("vis-network");
    this.canvas = document.createElement("div");
    this.canvas.className = "vis-fallback-list";
    this.container.innerHTML = "";
    this.container.appendChild(this.canvas);

    var rerender = this.render.bind(this);
    if (this.data.nodes && this.data.nodes._subscribe) this.data.nodes._subscribe(rerender);
    if (this.data.edges && this.data.edges._subscribe) this.data.edges._subscribe(rerender);

    this.container.addEventListener("click", function (event) {
      if (event.target === this.container || event.target === this.canvas) {
        this.selectedNodeId = null;
        this._emit("click", { nodes: [] });
      }
    }.bind(this));

    this._syncModesFromOptions(this.options);
    this.render();
  }

  Network.prototype._emit = function (eventName, payload) {
    var list = this.handlers[eventName] || [];
    list.forEach(function (handler) { handler(payload || {}); });
  };

  Network.prototype.on = function (eventName, handler) {
    if (!this.handlers[eventName]) this.handlers[eventName] = [];
    this.handlers[eventName].push(handler);
  };

  Network.prototype._syncModesFromOptions = function (options) {
    var layout = options && options.layout && options.layout.hierarchical;
    var physics = options && options.physics;
    if (layout && typeof layout.enabled === "boolean") {
      this.layoutMode = layout.enabled ? "hierarchical" : "free";
    }
    if (physics && typeof physics.enabled === "boolean") {
      this.physicsEnabled = physics.enabled;
    }
  };

  Network.prototype.setOptions = function (options) {
    this.options = Object.assign({}, this.options, options || {});
    this._syncModesFromOptions(options || {});
    this.render();
  };

  Network.prototype.focus = function (nodeId) {
    this.selectedNodeId = nodeId;
    var target = this.canvas.querySelector('[data-node-id="' + String(nodeId).replace(/"/g, '&quot;') + '"]');
    if (target) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      target.focus();
    }
    this.render();
  };

  Network.prototype.fit = function () {
    this.container.scrollTo({ top: 0, left: 0, behavior: "smooth" });
    this.container.classList.remove("vis-fit-pulse");
    this.container.offsetHeight;
    this.container.classList.add("vis-fit-pulse");
  };

  Network.prototype._orderedNodes = function (nodes) {
    var ordered = nodes.slice();
    ordered.sort(function (a, b) { return String(a.id).localeCompare(String(b.id)); });
    if (this.physicsEnabled) {
      ordered.sort(function (a, b) {
        return String(a.label || a.id).localeCompare(String(b.label || b.id));
      });
    }
    return ordered;
  };

  Network.prototype.render = function () {
    var nodes = this._orderedNodes((this.data.nodes && this.data.nodes.get()) || []);
    this.canvas.innerHTML = "";
    this.canvas.dataset.layout = this.layoutMode;
    this.canvas.dataset.physics = this.physicsEnabled ? "on" : "off";

    nodes.forEach(function (node) {
      if (node.hidden) return;
      var button = document.createElement("button");
      button.type = "button";
      button.className = "vis-fallback-node";
      button.dataset.nodeId = String(node.id);
      button.textContent = node.label || String(node.id);
      button.style.opacity = String(node.opacity === undefined ? 1 : node.opacity);
      if (node.color && node.color.background) button.style.background = node.color.background;
      if (node.borderWidth && node.borderWidth > 2) button.classList.add("vis-fallback-node-highlight");
      if (String(node.id) === String(this.selectedNodeId)) button.classList.add("vis-fallback-node-selected");
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        this.selectedNodeId = node.id;
        this._emit("click", { nodes: [node.id] });
      }.bind(this));
      this.canvas.appendChild(button);
    }, this);
  };

  window.vis = { DataSet: DataSet, Network: Network };
})();
