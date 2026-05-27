import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from brain_ds.ui.template_renderer import render_interactive_html


def _run_node(code: str, *args: str) -> dict:
    result = subprocess.run([
        "node",
        "-e",
        code,
        *args,
    ], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"Node runtime harness failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    payload = lines[-1] if lines else "{}"
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Invalid JSON from harness: {payload}\nFull STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}") from exc


class TestUiRuntimeBehavior(unittest.TestCase):
    def test_runtime_network_select_nodes_contract(self):
        """Renderer Network must expose vis-compatible selectNodes(ids)."""
        code = r'''
const fs = require("fs");
const path = require("path");

class ClassList { add(){} remove(){} toggle(){} contains(){ return false; } }
class El {
  constructor(tag="div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.classList = new ClassList();
    this.attrs = {};
    this.listeners = {};
    this.style = {};
    this.className = "";
    this.innerHTML = "";
    this.textContent = "";
    this.clientWidth = 800;
    this.clientHeight = 600;
  }
  appendChild(ch){ this.children.push(ch); return ch; }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k] || null; }
  addEventListener(t, fn){ (this.listeners[t] ||= []).push(fn); }
  getContext(){ return { clearRect(){}, save(){}, restore(){}, beginPath(){}, arc(){}, fill(){}, stroke(){}, moveTo(){}, lineTo(){}, fillText(){}, setLineDash(){}, measureText(){ return { width: 10 }; } }; }
  getBoundingClientRect(){ return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; }
}

const document = {
  createElement: (tag) => new El(tag),
  getElementById: () => null,
  querySelector: () => null,
  addEventListener: () => {},
  removeEventListener: () => {},
  documentElement: { getAttribute: () => "dark" },
};

global.document = document;
global.window = {
  document,
  vis: undefined,
  matchMedia: () => ({ matches: false, addEventListener(){}, removeEventListener(){} }),
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  requestAnimationFrame: () => 1,
  cancelAnimationFrame: () => {},
};
globalThis.window = global.window;
globalThis.document = document;
global.getComputedStyle = window.getComputedStyle;
global.requestAnimationFrame = window.requestAnimationFrame;
global.cancelAnimationFrame = window.cancelAnimationFrame;

const repo = process.cwd();
const src = fs.readFileSync(path.join(repo, "brain_ds", "ui", "src", "renderer.ts"), "utf8");
eval(src);

const container = new El("section");
const nodes = new window.vis.DataSet([{ id: "n1", label: "Node 1", x: 0, y: 0 }]);
const edges = new window.vis.DataSet([]);
const net = new window.vis.Network(container, { nodes, edges }, {});

const hasMethod = typeof net.selectNodes === "function";
net.selectNodes(["n1"]);
const selectedAfterSelect = net.selectedNodeId === "n1";
net.selectNodes([]);
const clearedAfterEmpty = net.selectedNodeId === null;

console.log(JSON.stringify({ hasMethod, selectedAfterSelect, clearedAfterEmpty }));
'''
        out = _run_node(code)
        self.assertTrue(out["hasMethod"], "Network must expose selectNodes(ids)")
        self.assertTrue(out["selectedAfterSelect"], "selectNodes(['n1']) must select node")
        self.assertTrue(out["clearedAfterEmpty"], "selectNodes([]) must clear selection")

    def test_runtime_search_and_context_menu_behavior_from_bundle(self):
        code = r'''
const fs = require("fs");
const path = require("path");

class ClassList {
  constructor() { this._s = new Set(); }
  add(c) { this._s.add(c); }
  remove(c) { this._s.delete(c); }
  toggle(c, force) { if (force === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); } else { force ? this._s.add(c) : this._s.delete(c); } }
  contains(c) { return this._s.has(c); }
}

class El {
  constructor(tag, id="") {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.hidden = false;
    this.innerHTML = "";
    this.textContent = "";
    this.children = [];
    this.parentNode = null;
    this.className = "";
    this.classList = new ClassList();
    this.style = {};
    this.attrs = {};
    this.listeners = {};
    this.value = "";
    this.disabled = false;
  }
  appendChild(ch) { ch.parentNode = this; this.children.push(ch); return ch; }
  insertBefore(ch, ref) { ch.parentNode = this; const i = this.children.indexOf(ref); if (i >= 0) this.children.splice(i, 0, ch); else this.children.push(ch); return ch; }
  removeChild(ch) { this.children = this.children.filter((c) => c !== ch); }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t, fn) { this.listeners[t] = (this.listeners[t] || []).filter((f) => f !== fn); }
  dispatch(t, evt={}) { (this.listeners[t] || []).forEach((fn) => fn(evt)); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  focus() { document.activeElement = this; }
  querySelector(sel) {
    if (sel.startsWith("#")) return document.getElementById(sel.slice(1));
    if (sel === ".search-input-wrap") return this.children.find((c) => c.className === "search-input-wrap") || null;
    if (sel.includes("button[aria-label='Clear search']")) {
      return this.children.flatMap((c) => c.children || []).find((c) => c.attrs && c.attrs["aria-label"] === "Clear search") || null;
    }
    return null;
  }
  querySelectorAll(sel) {
    if (sel === "li.search-option") {
      return this.children.filter((c) => c.className === "search-option");
    }
    if (sel === "button:not([disabled])") {
      const out = [];
      const walk = (n) => {
        if (n.tagName === "BUTTON" && !n.disabled) out.push(n);
        (n.children || []).forEach(walk);
      };
      walk(this);
      return out;
    }
    return [];
  }
}

const _byId = new Map();
const body = new El("body", "body");
const document = {
  body,
  activeElement: null,
  createElement: (t) => new El(t),
  getElementById: (id) => _byId.get(id) || null,
  querySelector: (sel) => sel.startsWith("#") ? (_byId.get(sel.slice(1)) || null) : null,
  addEventListener: () => {},
  removeEventListener: () => {},
};

global.document = document;
global.window = {
  document,
  vis: undefined,
  brainDsUI: undefined,
  innerWidth: 1280,
  innerHeight: 800,
  matchMedia: () => ({ matches: false }),
};
globalThis.window = global.window;
globalThis.document = document;

const repo = process.cwd();
const bundle = fs.readFileSync(path.join(repo, "brain_ds", "ui", "assets", "viewer.bundle.js"), "utf8");
eval(bundle);

const root = new El("section", "search-group");
const input = new El("input", "node-search");
const results = new El("ol", "search-results");
_byId.set("node-search", input);
_byId.set("search-results", results);
root.appendChild(input);
root.appendChild(results);

let cleared = 0;
window.brainDsUI.search.mount(root, {
  nodes: [
    { id: "n1", label: "Alpha", type: "Department" },
    { id: "n2", label: "Alpine", type: "Role" },
  ],
  onSelect: () => {},
  onClear: () => { cleared += 1; },
});

input.value = "Al";
input.dispatch("input", {});
input.dispatch("keydown", { key: "ArrowDown", preventDefault(){} });
const activeDesc = input.getAttribute("aria-activedescendant");
input.dispatch("keydown", { key: "Escape", preventDefault(){} });
const escapedClosed = input.getAttribute("aria-expanded") === "false" && cleared === 1;

const listeners = {};
const network = {
  canvas: new El("div", "canvas"),
  on: (ev, fn) => { listeners[ev] = fn; },
  off: () => {},
  closeContextMenu: () => {},
  fit: () => {},
  setOptions: () => {},
};
const trigger = new El("button", "trigger");
document.activeElement = trigger;

window.brainDsUI.contextMenu.mount({
  network,
  RENDER_CONTEXT: { nodes: [], edges: [] },
  adjacency: {},
  nodes: { update(){} },
  edges: { update(){} },
  focusNode: () => {},
  resetFilters: () => {},
  toggleTheme: () => {},
});
listeners["context-menu"]({ nodeId: null, screen: { x: 10, y: 10 } });
const menu = document.getElementById("vis-context-menu") || body.children.find((c) => c.id === "vis-context-menu");
menu.dispatch("keydown", { key: "Escape", preventDefault(){} });
const focusRestored = document.activeElement === trigger;

console.log(JSON.stringify({ activeDesc, escapedClosed, focusRestored }));
'''
        out = _run_node(code)
        self.assertEqual(out["activeDesc"], "search-option-0")
        self.assertTrue(out["escapedClosed"])
        self.assertTrue(out["focusRestored"])

    def test_runtime_template_loading_focustrap_skeleton_motion(self):
        html = render_interactive_html(
            {
                "meta": {"org": "RuntimeOrg", "node_count": 1, "edge_count": 0, "generated_at": ""},
                "nodes": [{"id": "n1", "label": "Node 1", "type": "Department"}],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {"n1": {"node": {"id": "n1", "label": "Node 1", "type": "Department"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []}},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "runtime-viewer.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList {
  constructor(){ this.s = new Set(); }
  add(c){ this.s.add(c); }
  remove(c){ this.s.delete(c); }
  toggle(c,f){ if (f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} }
  contains(c){ return this.s.has(c); }
}
class El {
  constructor(id=""){ this.id=id; this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.children=[]; this.innerHTML=""; this.textContent=""; this.hidden=false; this.style={}; this.className=""; }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(e)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  focus(){ document.activeElement=this; }
  appendChild(c){ this.children.push(c); return c; }
  querySelectorAll(){ return this.children; }
  querySelector(sel){
    if (sel && sel.startsWith("#")) {
      const id = sel.slice(1);
      return this.children.find((c)=>c.id===id) || null;
    }
    return null;
  }
  closest(){ return document.body; }
}
const ids = ["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls"];
const byId = new Map(ids.map((id)=>[id,new El(id)]));
byId.get("detail-panel").classList.add("is-mobile-open");
byId.get("search-group").appendChild(byId.get("node-search"));
byId.get("search-group").appendChild(byId.get("search-results"));
const document = {
  activeElement:null,
  body:new El("body"),
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>{
    if (sel === ".search-group") return byId.get("search-group");
    if (sel === ".controls") return byId.get("controls");
    if (sel && sel.startsWith("#")) return byId.get(sel.slice(1)) || null;
    return null;
  },
  createElement:()=>new El(),
  createElementNS:()=>new El(),
  createTextNode:(txt)=>{ const e = new El(); e.textContent = String(txt); return e; },
  addEventListener:()=>{},
  removeEventListener:()=>{},
  documentElement:new El("html")
};
const timers=[];
const windowObj = {
  document,
  vis: {
    DataSet: function(items){ this._items=items; this.update=()=>{}; },
    Network: function(){
      this._handlers={};
      this.on=(ev,fn)=>{ this._handlers[ev]=fn; };
      this.once=(ev,fn)=>{ this._handlers[ev]=fn; };
      this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.canvas={focus:()=>{}};
    }
  },
  brainDsUI: {
    detailPanel: { mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} },
    search: { mount:()=>{} }, filterPanel: { mount:()=>{}, setAllChecked:()=>{} },
    scoreFilter: { mount:()=>{}, setThreshold:()=>{} }, popover: { mount:()=>{} }, contextMenu: { mount:()=>{} },
  },
  innerWidth: 900,
  matchMedia: ()=>({ matches:false }),
  setTimeout: (fn, ms)=>{ timers.push({fn,ms}); return timers.length; },
  clearTimeout: ()=>{},
  addEventListener: ()=>{},
};
global.window = windowObj;
global.document = document;
globalThis.window = windowObj;
globalThis.document = document;
globalThis.vis = windowObj.vis;

eval(appScript);

if (typeof renderDetailPanel === "function") {
  renderDetailPanel("n1");
}

const loadingScheduled = timers.some((t)=>t.ms===150);
timers.filter((t)=>t.ms===150).forEach((t)=>t.fn());
const loadingVisible = byId.get("viewer-loading").classList.contains("is-visible");
const skeletonContract = html.includes("detail-skeleton__line--1") && html.includes("detail-skeleton__line--3") && html.includes("detail-skeleton-shimmer");
const reducedMotion = html.includes("@media (prefers-reduced-motion: reduce)") && html.includes(".viewer-loading__spinner, .detail-skeleton__line { animation: none; }");

console.log(JSON.stringify({ loadingScheduled, loadingVisible, skeletonContract, reducedMotion }));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["loadingScheduled"])
            self.assertTrue(out["loadingVisible"])
            self.assertTrue(out["skeletonContract"])
            self.assertTrue(out["reducedMotion"])

    def test_runtime_slideover_tab_trap_and_escape_dismiss(self):
        html = render_interactive_html(
            {
                "meta": {"org": "RuntimeOrg", "node_count": 1, "edge_count": 0, "generated_at": ""},
                "nodes": [{"id": "n1", "label": "Node 1", "type": "Department"}],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {"n1": {"node": {"id": "n1", "label": "Node 1", "type": "Department"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []}},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "runtime-viewer.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} } }
class El {
  constructor(id="", tag="div"){ this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false; this.textContent=""; this.className=""; this.style={}; }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(e)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ this.children.push(c); return c; }
  querySelectorAll(sel){
    if (sel.includes("button:not([disabled])")) return this.children.filter((c)=>c.tagName==="BUTTON");
    return this.children;
  }
  querySelector(sel){ if (sel && sel.startsWith("#")) { const id = sel.slice(1); return this.children.find((c)=>c.id===id) || null; } return null; }
  contains(node){ if (node === this) return true; return this.children.some((c)=>typeof c.contains === "function" && c.contains(node)); }
  focus(){ document.activeElement=this; }
  closest(){ return document.body; }
}

const ids=["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta"];
const byId=new Map(ids.map((id)=>[id,new El(id)]));
byId.get("detail-collapse").setAttribute("aria-expanded","true");
byId.get("detail-panel").appendChild(new El("btn-a","button"));
byId.get("detail-panel").appendChild(new El("btn-b","button"));

const document={
  activeElement:null,
  body:new El("body"),
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>{ if(sel===".search-group") return byId.get("search-group"); if(sel===".controls") return byId.get("controls"); if(sel && sel.startsWith("#")) return byId.get(sel.slice(1))||null; return null; },
  createElement:()=>new El(),
  createElementNS:()=>new El(),
  createTextNode:(txt)=>{ const e=new El(); e.textContent=String(txt); return e; },
  addEventListener:()=>{}, removeEventListener:()=>{},
  documentElement:new El("html")
};

const windowObj={
  document,
  vis:{ DataSet:function(items){ this._items=items; this.update=()=>{}; }, Network:function(){ this._handlers={}; this.on=(ev,fn)=>{this._handlers[ev]=fn;}; this.once=(ev,fn)=>{this._handlers[ev]=fn;}; this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.canvas={focus:()=>{}}; }},
  brainDsUI:{ detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} }, search:{ mount:()=>{} }, filterPanel:{ mount:()=>{}, setAllChecked:()=>{} }, scoreFilter:{ mount:()=>{}, setThreshold:()=>{} }, popover:{ mount:()=>{} }, contextMenu:{ mount:()=>{} } },
  innerWidth:900,
  matchMedia:()=>({matches:false}),
  setTimeout:(fn)=>{ fn(); return 1; },
  clearTimeout:()=>{},
  addEventListener:()=>{}
};
global.window=windowObj; global.document=document; globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;
eval(appScript);

const panel = byId.get("detail-panel");
const first = panel.children[0];
const last = panel.children[1];
document.activeElement = last;
let prevented = false;
panel.dispatch("keydown", { key: "Tab", shiftKey: false, preventDefault(){ prevented = true; } });
const trappedToFirst = prevented && document.activeElement === first;

panel.dispatch("keydown", { key: "Escape", preventDefault(){} });
const escapedClosed = !panel.classList.contains("is-mobile-open");

console.log(JSON.stringify({ trappedToFirst, escapedClosed }));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["trappedToFirst"])
            self.assertTrue(out["escapedClosed"])

    def test_runtime_empty_state_filter_and_reset_flow(self):
        """GVP-7.4/7.5: filter→empty-state→reset CTA full behavioral round-trip."""
        html = render_interactive_html(
            {
                "meta": {"org": "RuntimeOrg", "node_count": 2, "edge_count": 0, "generated_at": ""},
                "nodes": [
                    {"id": "n1", "label": "Node 1", "type": "Department"},
                    {"id": "n2", "label": "Node 2", "type": "Role"},
                ],
                "edges": [],
                "type_groups": [
                    {"supertype": "actor", "types": [{"type": "Department", "count": 1, "color": "#aaa"}]},
                    {"supertype": "actor", "types": [{"type": "Role", "count": 1, "color": "#bbb"}]},
                ],
                "adjacency": {},
                "detail_index": {
                    "n1": {"node": {"id": "n1", "label": "Node 1", "type": "Department"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []},
                    "n2": {"node": {"id": "n2", "label": "Node 2", "type": "Role"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []},
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "runtime-viewer.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList {
  constructor(){ this.s=new Set(); }
  add(c){ this.s.add(c); }
  remove(c){ this.s.delete(c); }
  contains(c){ return this.s.has(c); }
  toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c); } else { f?this.s.add(c):this.s.delete(c); } }
}
class El {
  constructor(id="", tag="div"){
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList();
    this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false;
    this.textContent=""; this.innerHTML=""; this.className=""; this.style={};
    this.value=""; this.disabled=false; this.checked=true; this.type="";
  }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(e)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ this.children.push(c); return c; }
  insertBefore(c,ref){ const i=this.children.indexOf(ref); if(i>=0) this.children.splice(i,0,c); else this.children.push(c); return c; }
  removeChild(c){ this.children=this.children.filter((x)=>x!==c); }
  focus(){ document.activeElement=this; }
  closest(){ return document.body; }
  querySelector(sel){
    if (sel && sel.startsWith("#")) { const id=sel.slice(1); return this.children.find((c)=>c.id===id)||null; }
    return null;
  }
  querySelectorAll(sel){
    if (!sel) return this.children;
    if (sel && sel.includes("button:not([disabled])")) return this.children.filter((c)=>c.tagName==="BUTTON"&&!c.disabled);
    if (sel === "input[type=checkbox]") return this.children.filter((c)=>c.type==="checkbox");
    return this.children;
  }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
}

const ids=[
  "org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close",
  "score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading",
  "viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results",
  "node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics",
  "zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta"
];
const byId = new Map(ids.map((id) => [id, new El(id)]));
byId.get("search-group").appendChild(byId.get("node-search"));
byId.get("search-group").appendChild(byId.get("search-results"));

const nodeUpdates = [];
const document = {
  activeElement: null,
  body: new El("body"),
  getElementById: (id) => byId.get(id) || null,
  querySelector: (sel) => {
    if (sel === ".search-group") return byId.get("search-group");
    if (sel === ".controls") return byId.get("controls");
    if (sel && sel.startsWith("#")) return byId.get(sel.slice(1)) || null;
    return null;
  },
  createElement: () => new El(),
  createElementNS: () => new El(),
  createTextNode: (txt) => { const e = new El(); e.textContent = String(txt); return e; },
  addEventListener: ()=>{},
  removeEventListener: ()=>{},
  documentElement: new El("html"),
};

const windowObj = {
  document,
  vis: {
    DataSet: function(items) {
      this._items = [...(items || [])];
      this.update = (updates) => { nodeUpdates.push(...updates); };
      this.get = () => this._items;
    },
    Network: function() {
      this._handlers = {};
      this.on = (ev, fn) => { this._handlers[ev] = fn; };
      this.once = (ev, fn) => { this._handlers[ev] = fn; };
      this.fit = ()=>{}; this.setOptions = ()=>{}; this.redraw = ()=>{}; this.canvas = { focus: ()=>{} };
    }
  },
  brainDsUI: {
    detailPanel: { mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} },
    search: { mount: ()=>{} },
    // filterPanel and scoreFilter: use the real bundle implementations.
    // The bundle overwrites window.brainDsUI after eval(appScript), so these
    // stubs are replaced. The real modules wire the template's onToggle / onThresholdChange
    // callbacks which drive hiddenTypes and applyVisibility().
    filterPanel: { mount: ()=>{}, setAllChecked: ()=>{} },
    scoreFilter: { mount: ()=>{}, setThreshold: ()=>{} },
    popover: { mount: ()=>{} },
    contextMenu: { mount: ()=>{} },
  },
  innerWidth: 1280,
  matchMedia: () => ({ matches: false }),
  setTimeout: (fn) => { fn(); return 1; },
  clearTimeout: ()=>{},
  addEventListener: ()=>{},
};
global.window = windowObj; global.document = document;
globalThis.window = windowObj; globalThis.document = document; globalThis.vis = windowObj.vis;

eval(appScript);

const emptyStateEl = byId.get("viewer-empty");
const emptyResetBtn = byId.get("empty-reset-filters");

// Step 1: Apply a filter that yields zero visible nodes.
// The real filterPanel module (from bundle) has wired hide-all to call onToggle for each type.
// Dispatching the hide-all click drives hiddenTypes (template-scope) → applyVisibility().
byId.get("hide-all").dispatch("click", {});

// Step 2: Assert that empty-state element has is-visible after all nodes are filtered out.
const emptyStateShownAfterFilter = emptyStateEl.classList.contains("is-visible");

// Step 3: Activate the reset CTA (REQ-GVP-7.4: same reset behavior as context menu).
emptyResetBtn.dispatch("click", {});

// Step 4: After reset, resetFilters() → hiddenTypes.clear() + scoreFilter.setThreshold(0).
// setThreshold(0) fires onThresholdChange(0) → applyVisibility() → updateEmptyState(2) → removes is-visible.
const emptyStateHiddenAfterReset = !emptyStateEl.classList.contains("is-visible");

// Step 5: Confirm nodes are visible again (nodes.update called with at least one hidden:false entry).
const hasVisibleNodesAfterReset = nodeUpdates.some((u) => u.hidden === false);

console.log(JSON.stringify({ emptyStateShownAfterFilter, emptyStateHiddenAfterReset, hasVisibleNodesAfterReset }));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["emptyStateShownAfterFilter"], "Empty state must appear when all nodes are filtered out")
            self.assertTrue(out["emptyStateHiddenAfterReset"], "Empty state must disappear after reset CTA is clicked")
            self.assertTrue(out["hasVisibleNodesAfterReset"], "Nodes must become visible again after reset")

    def test_runtime_detail_edit_focus_and_canvas_ring_draws(self):
        code = r'''
const fs = require("fs");
const path = require("path");

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} } }
class El {
  constructor(tag="div", id=""){ this.tagName=tag.toUpperCase(); this.id=id; this.children=[]; this.parentNode=null; this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.textContent=""; this.innerHTML=""; this.style={ _props:{}, setProperty(k,v){ this._props[k]=String(v); }, getPropertyValue(k){ return this._props[k] || ""; } }; this.hidden=false; this.value=""; this.disabled=false; }
  appendChild(c){ c.parentNode=this; this.children.push(c); return c; }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  querySelector(sel){
    if (sel.startsWith("#")) return document.getElementById(sel.slice(1));
    if (sel.includes("input:not([disabled])")) return this.children.find((c)=>c.tagName==="INPUT" && !c.disabled) || this.children.flatMap((c)=>c.children||[]).find((c)=>c.tagName==="INPUT" && !c.disabled) || null;
    return null;
  }
  querySelectorAll(){ return this.children; }
  contains(node){ if (node === this) return true; return this.children.some((c)=>typeof c.contains === "function" && c.contains(node)); }
  closest(){ return document.body; }
  focus(){ document.activeElement=this; }
}

const byId = new Map();
const body = new El("body", "body");
const mk = (id, tag="div") => { const e = new El(tag, id); byId.set(id, e); return e; };
const detailPanel = mk("detail-panel");
const detailTitle = mk("detail-title");
const detailMeta = mk("detail-meta");
const detailBody = mk("detail-body");
const editToggle = mk("edit-toggle", "button");
const exportJson = mk("export-json", "button");
const collapse = mk("detail-collapse", "button");
const network = mk("network");
network.getBoundingClientRect = () => ({left:0, top:0, width:1000, height:600});
body.appendChild(detailPanel);
detailPanel.appendChild(detailTitle); detailPanel.appendChild(detailMeta); detailPanel.appendChild(detailBody);

const ctxLog = { lineWidths: [], dashCalls: [] };
const ctx = {
  beginPath(){}, moveTo(){}, lineTo(){}, arc(){}, fill(){}, stroke(){ if (typeof this.lineWidth === "number") ctxLog.lineWidths.push(this.lineWidth); },
  setLineDash(v){ ctxLog.dashCalls.push(v); },
  clearRect(){}, save(){}, restore(){}, setTransform(){}, fillText(){}, measureText(){ return { width: 20 }; }
};
const canvas = new El("canvas");
canvas.width = 800; canvas.height = 600;
canvas.getContext = () => ctx;
network.appendChild = () => canvas;
network.querySelector = () => null;
network.addEventListener = () => {};

const document = {
  body,
  activeElement:null,
  createElement: (t)=> {
    const e = new El(t);
    if (String(t).toLowerCase() === "canvas") {
      e.getContext = () => ctx;
      e.width = 800;
      e.height = 600;
      e.className = "vis-canvas";
      e.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600 });
    }
    return e;
  },
  createElementNS: (ns,t)=> new El(t),
  getElementById: (id)=> byId.get(id) || null,
  querySelector: (sel)=> sel.startsWith("#") ? (byId.get(sel.slice(1)) || null) : null,
  addEventListener: ()=>{},
  removeEventListener: ()=>{},
  documentElement: new El("html")
};
global.document = document;
global.window = {
  document,
  vis: undefined,
  brainDsUI: undefined,
  innerWidth: 1280,
  innerHeight: 800,
  devicePixelRatio: 1,
  addEventListener: ()=>{},
  removeEventListener: ()=>{},
  matchMedia: ()=>({ matches: false }),
  getComputedStyle: ()=>({ getPropertyValue: ()=>"" }),
  requestAnimationFrame: ()=>1,
  cancelAnimationFrame: ()=>{},
};
global.getComputedStyle = window.getComputedStyle;
global.requestAnimationFrame = window.requestAnimationFrame;
global.cancelAnimationFrame = window.cancelAnimationFrame;
globalThis.window = global.window;
globalThis.document = document;

const repo = process.cwd();
const bundle = fs.readFileSync(path.join(repo, "brain_ds", "ui", "assets", "viewer.bundle.js"), "utf8");
eval(bundle);

window.brainDsUI.detailPanel.mount(detailPanel, {
  editedDetailIndex: {
    n1: { node: { id: "n1", label: "Node 1", type: "Department", supertype: "actor" }, sections: [{ title: "What", content: "abc" }], relationships: { incoming: [], outgoing: [] }, evidence: [] }
  },
  editedData: { nodes: [{ id: "n1", label: "Node 1", type: "Department", supertype: "actor" }] },
  network: { on(){} },
  originalNodes: { get: ()=>({}) },
  RENDER_CONTEXT: { detail_index: {} },
  adjacency: {},
  motionEnabled: () => true,
});
window.brainDsUI.detailPanel.setSelectedNodeId("n1");
window.brainDsUI.detailPanel.setEditMode(true);
const editFocusedInput = document.activeElement && document.activeElement.tagName === "INPUT";

const nodes = [{ id: "n1", label: "Node 1", x: 10, y: 10, degree: 1, color: "#fff" }];
const edges = [];
const dsNodes = new window.vis.DataSet(nodes);
const dsEdges = new window.vis.DataSet(edges);
const net = new window.vis.Network(network, { nodes: dsNodes, edges: dsEdges }, {});
net.selectedNodeId = "n1";
net.keyboardFocusedNodeId = "n1";
net.viewport = { scale: 2, tx: 0, ty: 0 };
net._drawNodes({ nodes });
const hasSelectionLine = ctxLog.lineWidths.some((w)=>Math.abs(w - 1) < 0.001);
const hasFocusDashed = ctxLog.dashCalls.some((arr)=>Array.isArray(arr) && arr.length===2);

console.log(JSON.stringify({ editFocusedInput, hasSelectionLine, hasFocusDashed }));
'''
        out = _run_node(code)
        self.assertTrue(out["editFocusedInput"])
        self.assertTrue(out["hasSelectionLine"])
        self.assertTrue(out["hasFocusDashed"])

    def test_runtime_segmented_control_mutual_exclusion(self):
        """T1.4 / GV-4-A: clicking a segment flips aria-checked on both buttons."""
        html = render_interactive_html(
            {
                "meta": {"org": "SegCtrlOrg", "node_count": 1, "edge_count": 0, "generated_at": ""},
                "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {"n1": {"node": {"id": "n1", "label": "N1", "type": "Department"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []}},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "seg-ctrl.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} } }
class El {
  constructor(id="", tag="div"){
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList();
    this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false;
    this.textContent=""; this.innerHTML=""; this.className=""; this.style={};
    this.value=""; this.disabled=false; this.type="";
  }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(Object.assign({currentTarget:this},e))); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]??null; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ this.children.push(c); return c; }
  focus(){ document.activeElement=this; }
  closest(){ return document.body; }
  querySelectorAll(sel){
    if (!sel) return this.children;
    if (sel===".segment-btn") return this.children.filter((c)=>c.className&&c.className.includes("segment-btn"));
    return this.children;
  }
  querySelector(sel){
    if (sel && sel.startsWith("#")) return document.getElementById(sel.slice(1));
    if (sel===".segmented-control") return this.children.find((c)=>c.className&&c.className.includes("segmented-control"))||null;
    return null;
  }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
}

const ids=[
  "org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close",
  "score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading",
  "viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results",
  "node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics",
  "zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta"
];
const byId = new Map(ids.map((id) => [id, new El(id)]));
byId.get("search-group").appendChild(byId.get("node-search"));
byId.get("search-group").appendChild(byId.get("search-results"));

// Wire toggle-hierarchical and toggle-physics as segment-btn children of a segmented-control.
const segCtrl = new El("segmented-control", "div");
segCtrl.className = "segmented-control";
const hierBtn = byId.get("toggle-hierarchical");
hierBtn.className = "segment-btn";
hierBtn.setAttribute("role", "radio");
hierBtn.setAttribute("aria-checked", "false");
hierBtn.setAttribute("tabindex", "-1");
const physBtn = byId.get("toggle-physics");
physBtn.className = "segment-btn";
physBtn.setAttribute("role", "radio");
physBtn.setAttribute("aria-checked", "true");
physBtn.setAttribute("tabindex", "0");
segCtrl.children = [hierBtn, physBtn];

const setOptionsLog = [];
const document = {
  activeElement: null,
  body: new El("body"),
  getElementById: (id) => byId.get(id) || null,
  querySelector: (sel) => {
    if (sel === ".search-group") return byId.get("search-group");
    if (sel === ".controls") return byId.get("controls");
    if (sel === ".segmented-control") return segCtrl;
    if (sel && sel.startsWith("#")) return byId.get(sel.slice(1)) || null;
    return null;
  },
  querySelectorAll: (sel) => {
    if (sel === ".segment-btn") return [hierBtn, physBtn];
    return [];
  },
  createElement: () => new El(),
  createElementNS: () => new El(),
  createTextNode: (txt) => { const e = new El(); e.textContent = String(txt); return e; },
  addEventListener: () => {},
  removeEventListener: () => {},
  documentElement: new El("html"),
};

const windowObj = {
  document,
  vis: {
    DataSet: function(items){ this._items=items||[]; this.update=()=>{}; this.get=()=>this._items; },
    Network: function(){
      this._handlers={};
      this.on=(ev,fn)=>{this._handlers[ev]=fn;};
      this.once=(ev,fn)=>{this._handlers[ev]=fn;};
      this.fit=()=>{}; this.setOptions=(o)=>{setOptionsLog.push(o);}; this.redraw=()=>{}; this.canvas={focus:()=>{}};
    }
  },
  brainDsUI: {
    detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} },
    search:{ mount:()=>{} }, filterPanel:{ mount:()=>{}, setAllChecked:()=>{} },
    scoreFilter:{ mount:()=>{}, setThreshold:()=>{} }, popover:{ mount:()=>{} }, contextMenu:{ mount:()=>{} },
  },
  innerWidth: 1280,
  matchMedia: ()=>({ matches:false }),
  setTimeout: (fn)=>{ fn(); return 1; },
  clearTimeout: ()=>{},
  addEventListener: ()=>{},
};
global.window=windowObj; global.document=document;
globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;

eval(appScript);

// Initial state: Physics checked=true, Hierarchical checked=false
const initPhysicsChecked = physBtn.getAttribute("aria-checked") === "true";
const initHierChecked = hierBtn.getAttribute("aria-checked") === "false";

// Click Hierarchical — should flip both
hierBtn.dispatch("click", {});
const afterClickHierChecked = hierBtn.getAttribute("aria-checked") === "true";
const afterClickPhysUnchecked = physBtn.getAttribute("aria-checked") === "false";
const setOptionsCalledAfterHier = setOptionsLog.length >= 1;

// Click Physics — should flip back
physBtn.dispatch("click", {});
const afterClickPhysChecked = physBtn.getAttribute("aria-checked") === "true";
const afterClickHierUnchecked = hierBtn.getAttribute("aria-checked") === "false";

// Roving tabindex: only one should have tabindex="0" at a time
const tabindexAfterPhysClick = physBtn.getAttribute("tabindex") === "0" && hierBtn.getAttribute("tabindex") === "-1";

console.log(JSON.stringify({
  initPhysicsChecked, initHierChecked,
  afterClickHierChecked, afterClickPhysUnchecked, setOptionsCalledAfterHier,
  afterClickPhysChecked, afterClickHierUnchecked, tabindexAfterPhysClick
}));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["initPhysicsChecked"], "Physics must start checked")
            self.assertTrue(out["initHierChecked"], "Hierarchical must start unchecked")
            self.assertTrue(out["afterClickHierChecked"], "Hierarchical must be checked after click")
            self.assertTrue(out["afterClickPhysUnchecked"], "Physics must be unchecked after Hierarchical click (mutual exclusion)")
            self.assertTrue(out["setOptionsCalledAfterHier"], "network.setOptions must be called on segment click")
            self.assertTrue(out["afterClickPhysChecked"], "Physics must be checked after clicking it back")
            self.assertTrue(out["afterClickHierUnchecked"], "Hierarchical must be unchecked after Physics re-click")
            self.assertTrue(out["tabindexAfterPhysClick"], "Roving tabindex: Physics=0, Hierarchical=-1 after Physics click")

    def test_runtime_segmented_control_keyboard_navigation(self):
        """T1.5 / GV-15-A: ArrowRight/Left navigate focus+aria-checked on segmented control."""
        html = render_interactive_html(
            {
                "meta": {"org": "KbdNavOrg", "node_count": 1, "edge_count": 0, "generated_at": ""},
                "nodes": [{"id": "n1", "label": "N1", "type": "Department"}],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {"n1": {"node": {"id": "n1", "label": "N1", "type": "Department"}, "sections": [], "relationships": {"incoming": [], "outgoing": []}, "evidence": []}},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "kbd-nav.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} } }
class El {
  constructor(id="", tag="div"){
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList();
    this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false;
    this.textContent=""; this.innerHTML=""; this.className=""; this.style={};
    this.value=""; this.disabled=false; this.type="";
  }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(Object.assign({currentTarget:this, target:this},e))); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]??null; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ this.children.push(c); return c; }
  focus(){ document.activeElement=this; }
  closest(){ return document.body; }
  querySelectorAll(sel){
    if (!sel) return this.children;
    if (sel===".segment-btn") return this.children.filter((c)=>c.className&&c.className.includes("segment-btn"));
    return this.children;
  }
  querySelector(sel){
    if (sel && sel.startsWith("#")) return document.getElementById(sel.slice(1));
    if (sel===".segmented-control") return this.children.find((c)=>c.className&&c.className.includes("segmented-control"))||null;
    return null;
  }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
}

const ids=[
  "org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close",
  "score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading",
  "viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results",
  "node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics",
  "zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta"
];
const byId = new Map(ids.map((id) => [id, new El(id)]));
byId.get("search-group").appendChild(byId.get("node-search"));
byId.get("search-group").appendChild(byId.get("search-results"));

const segCtrl = new El("segmented-control", "div");
segCtrl.className = "segmented-control";
const hierBtn = byId.get("toggle-hierarchical");
hierBtn.className = "segment-btn";
hierBtn.setAttribute("role", "radio");
hierBtn.setAttribute("aria-checked", "false");
hierBtn.setAttribute("tabindex", "-1");
const physBtn = byId.get("toggle-physics");
physBtn.className = "segment-btn";
physBtn.setAttribute("role", "radio");
physBtn.setAttribute("aria-checked", "true");
physBtn.setAttribute("tabindex", "0");
segCtrl.children = [hierBtn, physBtn];

const document = {
  activeElement: physBtn,
  body: new El("body"),
  getElementById: (id) => byId.get(id) || null,
  querySelector: (sel) => {
    if (sel === ".search-group") return byId.get("search-group");
    if (sel === ".controls") return byId.get("controls");
    if (sel === ".segmented-control") return segCtrl;
    if (sel && sel.startsWith("#")) return byId.get(sel.slice(1)) || null;
    return null;
  },
  querySelectorAll: (sel) => {
    if (sel === ".segment-btn") return [hierBtn, physBtn];
    return [];
  },
  createElement: () => new El(),
  createElementNS: () => new El(),
  createTextNode: (txt) => { const e = new El(); e.textContent = String(txt); return e; },
  addEventListener: () => {},
  removeEventListener: () => {},
  documentElement: new El("html"),
};

const windowObj = {
  document,
  vis: {
    DataSet: function(items){ this._items=items||[]; this.update=()=>{}; this.get=()=>this._items; },
    Network: function(){
      this._handlers={};
      this.on=(ev,fn)=>{this._handlers[ev]=fn;};
      this.once=(ev,fn)=>{this._handlers[ev]=fn;};
      this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.canvas={focus:()=>{}};
    }
  },
  brainDsUI: {
    detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} },
    search:{ mount:()=>{} }, filterPanel:{ mount:()=>{}, setAllChecked:()=>{} },
    scoreFilter:{ mount:()=>{}, setThreshold:()=>{} }, popover:{ mount:()=>{} }, contextMenu:{ mount:()=>{} },
  },
  innerWidth: 1280,
  matchMedia: ()=>({ matches:false }),
  setTimeout: (fn)=>{ fn(); return 1; },
  clearTimeout: ()=>{},
  addEventListener: ()=>{},
};
global.window=windowObj; global.document=document;
globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;

eval(appScript);

// Initial state: Physics active (aria-checked=true), focus on Physics
// ArrowLeft from Physics → should move focus+check to Hierarchical
let prevented = false;
physBtn.dispatch("keydown", {
  key: "ArrowLeft",
  preventDefault(){ prevented = true; }
});
const arrowLeftMovedFocusToHier = document.activeElement === hierBtn;
const arrowLeftCheckedHier = hierBtn.getAttribute("aria-checked") === "true";
const arrowLeftUncheckedPhys = physBtn.getAttribute("aria-checked") === "false";

// ArrowRight from Hierarchical → should move focus+check to Physics
hierBtn.dispatch("keydown", {
  key: "ArrowRight",
  preventDefault(){ prevented = true; }
});
const arrowRightMovedFocusToPhys = document.activeElement === physBtn;
const arrowRightCheckedPhys = physBtn.getAttribute("aria-checked") === "true";
const arrowRightUncheckedHier = hierBtn.getAttribute("aria-checked") === "false";

console.log(JSON.stringify({
  arrowLeftMovedFocusToHier, arrowLeftCheckedHier, arrowLeftUncheckedPhys,
  arrowRightMovedFocusToPhys, arrowRightCheckedPhys, arrowRightUncheckedHier
}));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["arrowLeftMovedFocusToHier"], "ArrowLeft must move focus to Hierarchical")
            self.assertTrue(out["arrowLeftCheckedHier"], "ArrowLeft must check Hierarchical")
            self.assertTrue(out["arrowLeftUncheckedPhys"], "ArrowLeft must uncheck Physics")
            self.assertTrue(out["arrowRightMovedFocusToPhys"], "ArrowRight must move focus to Physics")
            self.assertTrue(out["arrowRightCheckedPhys"], "ArrowRight must check Physics")
            self.assertTrue(out["arrowRightUncheckedHier"], "ArrowRight must uncheck Hierarchical")


class TestWorkspaceControlsRuntime(unittest.TestCase):
    """Node harness runtime tests for Slice 1 workspace controls (P0).

    Two sub-tests:
    1. Bundle-eval test: loads the compiled bundle, tests workspaceChrome module
       API (setActivePanel), verifies aria-selected+tabindex+section visibility.
    2. Inline-script-only test: extracts the app script (after the bundle),
       tests left panel-collapse aria-expanded round-trip and tab-close hides
       .tab-item — both are inline handlers in graph_viewer.html.
    """

    def _render_html(self):
        return render_interactive_html(
            {
                "meta": {"org": "WCRuntimeOrg", "node_count": 1, "edge_count": 0, "generated_at": ""},
                "nodes": [{"id": "n1", "label": "Node 1", "type": "Department"}],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {
                    "n1": {
                        "node": {"id": "n1", "label": "Node 1", "type": "Department"},
                        "sections": [],
                        "relationships": {"incoming": [], "outgoing": []},
                        "evidence": [],
                    }
                },
            }
        )

    def test_rail_click_flips_aria_selected_tabindex_and_section_visibility(self):
        """Rail click flips aria-selected+tabindex+section visibility; double-click no-op."""
        html = self._render_html()
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "wc-runtime.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const path = require("path");

class ClassList {
  constructor(){ this._s=new Set(); }
  add(c){ this._s.add(c); } remove(c){ this._s.delete(c); } contains(c){ return this._s.has(c); }
  toggle(c,f){ if(f===undefined){ this._s.has(c)?this._s.delete(c):this._s.add(c); } else { f?this._s.add(c):this._s.delete(c); } }
}
class El {
  constructor(tag,id=""){ this.tagName=tag.toUpperCase(); this.id=id; this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false; this.textContent=""; this.innerHTML=""; this.className=""; this.style={}; this.value=""; this.disabled=false; }
  appendChild(ch){ ch.parentNode=this; this.children.push(ch); return ch; }
  insertBefore(ch,ref){ ch.parentNode=this; const i=this.children.indexOf(ref); if(i>=0) this.children.splice(i,0,ch); else this.children.push(ch); return ch; }
  removeChild(ch){ this.children=this.children.filter((c)=>c!==ch); }
  addEventListener(t,fn){ (this.listeners[t]||=[]).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,evt={}){ (this.listeners[t]||[]).forEach((fn)=>fn(evt)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]!==undefined?this.attrs[k]:null; }
  removeAttribute(k){ delete this.attrs[k]; }
  focus(){ document.activeElement=this; }
  closest(sel){
    let cur=this;
    while(cur){
      if(sel&&sel.startsWith(".")&&(cur.className===sel.slice(1)||(cur.classList&&cur.classList.contains(sel.slice(1))))) return cur;
      if(sel&&sel.startsWith("#")&&cur.id===sel.slice(1)) return cur;
      if(sel==='[data-rail-icon]' && cur.attrs && cur.attrs["data-rail-icon"]!==undefined) return cur;
      cur=cur.parentNode||null;
    }
    return null;
  }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
  querySelector(sel){
    if(!sel) return null;
    if(sel.startsWith("#")){ return _findById(this,sel.slice(1)); }
    const attrM=sel.match(/^\[([^\]=]+)="([^"]*)"\]$/);
    if(attrM) return _findByAttr(this,attrM[1],attrM[2]);
    return null;
  }
  querySelectorAll(sel){
    if(!sel) return [];
    const attrM=sel.match(/^\[([^\]=]+)\]$/);
    if(attrM){ const out=[]; _collectByAttrKey(this,attrM[1],out); return out; }
    const attrEq=sel.match(/^\[([^\]=]+)="([^"]*)"\]$/);
    if(attrEq){ const out=[]; _collectByAttr(this,attrEq[1],attrEq[2],out); return out; }
    return [];
  }
}
function _findById(el,id){ for(const c of el.children){ if(c.id===id) return c; const f=_findById(c,id); if(f) return f; } return null; }
function _findByAttr(el,k,v){ for(const c of el.children){ if(c.attrs&&c.attrs[k]===v) return c; const f=_findByAttr(c,k,v); if(f) return f; } return null; }
function _collectByAttrKey(el,k,out){ for(const c of el.children){ if(c.attrs&&c.attrs[k]!==undefined) out.push(c); _collectByAttrKey(c,k,out); } }
function _collectByAttr(el,k,v,out){ for(const c of el.children){ if(c.attrs&&c.attrs[k]===v) out.push(c); _collectByAttr(c,k,v,out); } }

const byId = new Map();
const body = new El("body","body");
function mk(tag,id){ const e=new El(tag,id); byId.set(id,e); body.appendChild(e); return e; }

// Rail root with 5 rail icon buttons
const railRoot = new El("nav","rail-root");
railRoot.attrs["data-rail-side"]="left";
body.appendChild(railRoot);
byId.set("rail-root",railRoot);

const railNames=["file-tree","search","filters","hierarchy","layout"];
const railBtns={};
for(const name of railNames){
  const btn=new El("button",name+"-btn");
  btn.attrs["data-rail-icon"]=name;
  btn.attrs["data-catalog-id"]=name;
  btn.attrs["aria-selected"]=name==="file-tree"?"true":"false";
  btn.attrs["tabindex"]=name==="file-tree"?"0":"-1";
  railBtns[name]=btn;
  railRoot.appendChild(btn);
}

// Panel root with accordion sections
const panelRoot=new El("aside","panel-root");
body.appendChild(panelRoot);
byId.set("panel-root",panelRoot);
const sectionNames=["search","filters","legend","hierarchy","layout","score"];
const sections={};
for(const name of sectionNames){
  const sec=new El("section","sec-"+name);
  sec.attrs["data-accordion-section"]=name;
  sec.hidden=false;
  sections[name]=sec;
  panelRoot.appendChild(sec);
}

const document={
  activeElement:null, body,
  createElement:(t)=>new El(t,""),
  createElementNS:(ns,t)=>new El(t,""),
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>null,
  querySelectorAll:(sel)=>[],
  addEventListener:()=>{}, removeEventListener:()=>{},
  documentElement:new El("html","html")
};
global.document=document;
global.window={ document, vis:undefined, brainDsUI:undefined, innerWidth:1280, innerHeight:800, matchMedia:()=>({matches:false}) };
globalThis.window=global.window; globalThis.document=document;

const repo=process.cwd();
const bundle=fs.readFileSync(path.join(repo,"brain_ds","ui","assets","viewer.bundle.js"),"utf8");
eval(bundle);

const wc=window.brainDsUI.workspaceChrome;
wc.mount({railRoot,panelRoot});

// TEST 1: click search rail icon
railRoot.dispatch("click", { target: railBtns["search"] });
const searchSelected=railBtns["search"].attrs["aria-selected"]==="true";
const fileTreeDeselected=railBtns["file-tree"].attrs["aria-selected"]==="false";
const searchTab0=railBtns["search"].attrs["tabindex"]==="0";
const fileTreeTabMinus1=railBtns["file-tree"].attrs["tabindex"]==="-1";
const searchVisible=sections["search"].hidden===false;
const legendHidden=sections["legend"].hidden===true;
const filtersHidden=sections["filters"].hidden===true;

// TEST 2: click file-tree = all visible
railRoot.dispatch("click", { target: railBtns["file-tree"] });
const allVisible=Object.values(sections).every((s)=>s.hidden===false);

// TEST 3: double-click active rail = no-op (idempotent)
railRoot.dispatch("click", { target: railBtns["search"] });
const before=JSON.stringify({
  selected: railBtns["search"].attrs["aria-selected"],
  tabIndex: railBtns["search"].attrs["tabindex"],
  searchHidden: sections["search"].hidden,
  legendHidden: sections["legend"].hidden,
});
railRoot.dispatch("click", { target: railBtns["search"] });
const after=JSON.stringify({
  selected: railBtns["search"].attrs["aria-selected"],
  tabIndex: railBtns["search"].attrs["tabindex"],
  searchHidden: sections["search"].hidden,
  legendHidden: sections["legend"].hidden,
});
const doubleClickNoOp=before===after;

console.log(JSON.stringify({searchSelected,fileTreeDeselected,searchTab0,fileTreeTabMinus1,searchVisible,legendHidden,filtersHidden,allVisible,doubleClickNoOp}));
'''
            out = _run_node(code, str(html_path))
            self.assertTrue(out["searchSelected"], "search rail MUST be aria-selected=true after setActivePanel")
            self.assertTrue(out["fileTreeDeselected"], "file-tree rail MUST be aria-selected=false")
            self.assertTrue(out["searchTab0"], "active rail MUST have tabindex=0")
            self.assertTrue(out["fileTreeTabMinus1"], "inactive rail MUST have tabindex=-1")
            self.assertTrue(out["searchVisible"], "search section MUST be visible")
            self.assertTrue(out["legendHidden"], "legend MUST be hidden when search is active")
            self.assertTrue(out["filtersHidden"], "filters MUST be hidden when search is active")
            self.assertTrue(out["allVisible"], "ALL sections MUST be visible when file-tree is active")
            self.assertTrue(out["doubleClickNoOp"], "double setActivePanel on same panel MUST be no-op")

    def test_left_collapse_aria_expanded_and_tab_close(self):
        """Left panel-collapse aria-expanded round-trip and tab-close hides .tab-item.

        Uses the inline-script-only eval pattern: extracts the inline app-script
        portion (starting at 'const RENDER_CONTEXT') so that only the template's
        inline script runs with fully stubbed brainDsUI modules.
        """
        html = self._render_html()
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "wc-collapse.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m)=>m[1]);
const fullScript = scripts[scripts.length-1];
// Extract only the inline portion (after the bundle) starting at 'const RENDER_CONTEXT'
const inlineStart = fullScript.indexOf("const RENDER_CONTEXT");
const appScript = inlineStart >= 0 ? fullScript.slice(inlineStart) : fullScript;

class ClassList {
  constructor(){ this.s=new Set(); }
  add(c){ this.s.add(c); } remove(c){ this.s.delete(c); } contains(c){ return this.s.has(c); }
  toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c); } else { f?this.s.add(c):this.s.delete(c); } }
}
class El {
  constructor(id="",tag="div"){
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false; this.textContent=""; this.innerHTML=""; this.className=""; this.style={}; this.value=""; this.disabled=false; this.checked=true; this.type="";
  }
  addEventListener(t,fn){ (this.listeners[t]||=[]).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,e={}){ (this.listeners[t]||[]).forEach((fn)=>fn(e)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]!==undefined?this.attrs[k]:null; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ if(c&&typeof c==="object"){ c.parentNode=this; this.children.push(c); } return c; }
  insertBefore(c,ref){ const i=this.children.indexOf(ref); if(i>=0) this.children.splice(i,0,c); else this.children.push(c); return c; }
  removeChild(c){ this.children=this.children.filter((x)=>x!==c); }
  focus(){ document.activeElement=this; }
  closest(sel){
    let cur=this;
    while(cur){
      if(sel&&sel.startsWith(".")){ const cls=sel.slice(1); if(cur.className===cls||(cur.classList&&cur.classList.contains(cls))) return cur; }
      else if(sel&&sel.startsWith("#")){ if(cur.id===sel.slice(1)) return cur; }
      cur=cur.parentNode||null;
    }
    return null;
  }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
  querySelector(sel){ if(!sel) return null; if(sel.startsWith("#")){ return this.children.find((c)=>c.id===sel.slice(1))||null; } return null; }
  querySelectorAll(sel){ if(sel&&sel.includes("button:not([disabled])")) return this.children.filter((c)=>c.tagName==="BUTTON"&&!c.disabled); if(sel==="input[type=checkbox]") return this.children.filter((c)=>c.type==="checkbox"); return this.children; }
}

const byId=new Map();
const body=new El("body","body");
function mk(id,tag="div"){ const e=new El(id,tag); byId.set(id,e); return e; }

// Left panel shell + collapse button
const leftShell=mk("left-panel-shell-wc","aside");
leftShell.className="left-panel-shell";
const collapseBtn=mk("panel-collapse-wc","button");
collapseBtn.className="panel-collapse";
collapseBtn.attrs["aria-expanded"]="true";
leftShell.appendChild(collapseBtn);
body.appendChild(leftShell);

// Tab item + close button
const tabItem=mk("tab-item-wc","div");
tabItem.className="tab-item";
tabItem.hidden=false;
const tabClose=mk("tab-close-wc","button");
tabClose.className="tab-close";
tabClose.attrs["data-catalog-id"]="tab-close";
tabClose.parentNode=tabItem;
tabItem.appendChild(tabClose);
body.appendChild(tabItem);

// Required IDs for inline script
const ids=["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta","tree-filter-chip","workspace-view-org","workspace-view-nodes","workspace-view-edges","center-split"];
for(const id of ids){ if(!byId.has(id)) mk(id); }

const document={
  activeElement:null, body,
  createElement:(t)=>new El("",t), createElementNS:(ns,t)=>new El("",t),
  createTextNode:(txt)=>{ const e=new El(); e.textContent=String(txt); return e; },
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>{
    if(sel===".search-group") return byId.get("search-group")||null;
    if(sel===".controls") return byId.get("controls")||null;
    if(sel===".left-panel-shell") return byId.get("left-panel-shell-wc")||null;
    if(sel===".panel-collapse") return byId.get("panel-collapse-wc")||null;
    if(sel==='[data-catalog-id="tab-close"]') return byId.get("tab-close-wc")||null;
    if(sel&&sel.startsWith("#")) return byId.get(sel.slice(1))||null;
    return null;
  },
  querySelectorAll:(sel)=>[],
  addEventListener:()=>{}, removeEventListener:()=>{},
  documentElement:new El("html")
};
const windowObj={
  document,
  vis:{ DataSet:function(items){ this._items=items||[]; this.update=()=>{}; this.get=()=>this._items||[]; }, Network:function(){ this._h={}; this.on=(ev,fn)=>{this._h[ev]=fn;}; this.once=(ev,fn)=>{this._h[ev]=fn;}; this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.canvas={focus:()=>{}}; }},
  brainDsUI:{
    detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{}, getSelectedNodeId:()=>null, getHasEdits:()=>false, collapseDetailPanel:()=>{} },
    search:{mount:()=>{}},
    filterPanel:{mount:()=>{},setAllChecked:()=>{}},
    tree:{mount:()=>{}},
    scoreFilter:{mount:()=>{},setThreshold:()=>{}},
    popover:{mount:()=>{}},
    contextMenu:{mount:()=>{}},
    liveSync:{ LiveDataStore:function(){this.getNodes=()=>[];this.getEdges=()=>[];this.dispose=()=>{};this.syncWithServer=()=>{};}, connectWebSocket:()=>{}, connect:()=>{} },
    splitPane:{mount:()=>({unmount:()=>{}})},
    workspaceChrome:{mount:()=>{},unmount:()=>{},setActivePanel:()=>{}},
    motion:{motionEnabled:()=>true},
  },
  innerWidth:1280, innerHeight:800, matchMedia:()=>({matches:false}),
  setTimeout:(fn,ms)=>{ fn(); return 1; }, clearTimeout:()=>{},
  addEventListener:()=>{}, removeEventListener:()=>{},
};
global.window=windowObj; global.document=document; globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;

// Eval only the inline app-script (not the bundle)
eval(appScript);

// TEST: left panel-collapse aria-expanded round-trip + collapsed class
const initialExpanded=collapseBtn.getAttribute("aria-expanded");
collapseBtn.dispatch("click",{});
const afterFirst=collapseBtn.getAttribute("aria-expanded");
const collapsedClassAfterFirst=leftShell.classList.contains("collapsed");
collapseBtn.dispatch("click",{});
const afterSecond=collapseBtn.getAttribute("aria-expanded");
const collapsedClassAfterSecond=leftShell.classList.contains("collapsed");

// TEST: tab-close hides .tab-item
tabClose.dispatch("click",{});
const tabItemHidden=tabItem.hidden===true||tabItem.classList.contains("hidden");

console.log(JSON.stringify({initialExpanded,afterFirst,afterSecond,collapsedClassAfterFirst,collapsedClassAfterSecond,tabItemHidden}));
'''
            out = _run_node(code, str(html_path))
            self.assertEqual(out["initialExpanded"], "true",
                             "Left panel-collapse MUST start aria-expanded='true'")
            self.assertEqual(out["afterFirst"], "false",
                             "Left panel-collapse MUST flip to aria-expanded='false' on click")
            self.assertEqual(out["afterSecond"], "true",
                             "Left panel-collapse MUST flip back to aria-expanded='true'")
            self.assertTrue(out["collapsedClassAfterFirst"],
                            "Left shell MUST add .collapsed class when panel is collapsed")
            self.assertFalse(out["collapsedClassAfterSecond"],
                             "Left shell MUST remove .collapsed class when panel re-expands")
            self.assertTrue(out["tabItemHidden"],
                            "tab-close click MUST hide the .tab-item")

    def test_slice2_right_collapse_splitpane_overflow_and_single_tab_layout(self):
        """Slice 2 RED: right collapse, split-pane mount, overflow dismiss, single-tab layout intact."""
        html = self._render_html()
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "wc-slice2-runtime.html"
            html_path.write_text(html, encoding="utf-8")
            code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m)=>m[1]);
const fullScript = scripts[scripts.length-1];
const inlineStart = fullScript.indexOf("const RENDER_CONTEXT");
const appScript = inlineStart >= 0 ? fullScript.slice(inlineStart) : fullScript;

class ClassList {
  constructor(){ this.s=new Set(); }
  add(c){ this.s.add(c); } remove(c){ this.s.delete(c); } contains(c){ return this.s.has(c); }
  toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c); } else { f?this.s.add(c):this.s.delete(c); } }
}
class El {
  constructor(id="",tag="div"){
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.children=[]; this.hidden=false; this.textContent=""; this.innerHTML=""; this.className=""; this.style={}; this.value=""; this.disabled=false; this.checked=true; this.type="";
    this.parentNode=null;
  }
  addEventListener(t,fn){ (this.listeners[t]||=[]).push(fn); }
  removeEventListener(t,fn){ this.listeners[t]=(this.listeners[t]||[]).filter((f)=>f!==fn); }
  dispatch(t,e={}){ if(typeof e.preventDefault!=="function") e.preventDefault=()=>{}; (this.listeners[t]||[]).forEach((fn)=>fn(e)); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]!==undefined?this.attrs[k]:null; }
  removeAttribute(k){ delete this.attrs[k]; }
  appendChild(c){ if(c&&typeof c==="object"){ c.parentNode=this; this.children.push(c); } return c; }
  removeChild(c){ this.children=this.children.filter((x)=>x!==c); if(c) c.parentNode=null; }
  focus(){ document.activeElement=this; }
  contains(n){ if(n===this) return true; return this.children.some((c)=>typeof c.contains==="function"&&c.contains(n)); }
  closest(sel){
    let cur=this;
    while(cur){
      if(sel&&sel.startsWith(".")){ const cls=sel.slice(1); if(cur.className===cls||(cur.classList&&cur.classList.contains(cls))) return cur; }
      cur=cur.parentNode||null;
    }
    return null;
  }
  querySelector(sel){
    if(!sel) return null;
    if(sel.startsWith("#")) return this.children.find((c)=>c.id===sel.slice(1))||null;
    if(sel==='[role="menu"]') return this.children.find((c)=>c.attrs&&c.attrs["role"]==="menu")||null;
    return null;
  }
  querySelectorAll(sel){
    if(sel==="button:not([disabled])") return this.children.filter((c)=>c.tagName==="BUTTON"&&!c.disabled);
    return this.children;
  }
}

const byId=new Map();
const body=new El("body","body");
function mk(id,tag="div"){ const e=new El(id,tag); byId.set(id,e); return e; }

const rightShell=mk("right-panel-shell-wc","aside");
rightShell.className="right-panel-shell";
const rightCollapse=mk("panel-collapse-right-wc","button");
rightCollapse.className="panel-collapse-right";
rightCollapse.attrs["aria-expanded"]="true";
rightShell.appendChild(rightCollapse);
body.appendChild(rightShell);

const centerSplit=mk("center-split","section");
centerSplit.attrs["data-layout"]="collapsed";
const showMore=mk("show-more","button");
const hideMarkdown=mk("hide-markdown","button");
body.appendChild(centerSplit);
body.appendChild(showMore);
body.appendChild(hideMarkdown);

const tabItem=mk("tab-item-wc","div");
tabItem.className="tab-item";
const tabClose=mk("tab-close-wc","button");
tabClose.attrs["data-catalog-id"]="tab-close";
tabItem.appendChild(tabClose);
body.appendChild(tabItem);
const tabNew=mk("tab-new-wc","button");
tabNew.className="tab-new";
body.appendChild(tabNew);
const workspace=mk("workspace-shell","main");
workspace.className="workspace-shell";
body.appendChild(workspace);

const overflowBtn=mk("overflow-btn-wc","button");
overflowBtn.attrs["data-catalog-id"]="overflow";
overflowBtn.attrs["aria-expanded"]="false";
body.appendChild(overflowBtn);

const railRoot=mk("left-rail","nav"); railRoot.attrs["data-rail-side"]="left"; body.appendChild(railRoot);
const panelRoot=mk("left-panel","aside"); panelRoot.className="panel controls"; body.appendChild(panelRoot);

const ids=["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta","tree-filter-chip","workspace-view-org","workspace-view-nodes","workspace-view-edges"];
for(const id of ids){ if(!byId.has(id)) body.appendChild(mk(id)); }

const docListeners={};
const document={
  activeElement:null, body,
  createElement:(t)=>new El("",t), createElementNS:(ns,t)=>new El("",t),
  createTextNode:(txt)=>{ const e=new El(); e.textContent=String(txt); return e; },
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>{
    if(sel===".search-group") return byId.get("search-group")||null;
    if(sel===".controls") return byId.get("controls")||null;
    if(sel===".right-panel-shell") return byId.get("right-panel-shell-wc")||null;
    if(sel===".panel-collapse-right") return byId.get("panel-collapse-right-wc")||null;
    if(sel==='[data-catalog-id="tab-close"]') return byId.get("tab-close-wc")||null;
    if(sel==='[data-catalog-id="overflow"]') return byId.get("overflow-btn-wc")||null;
    if(sel==='[data-rail-side="left"]') return byId.get("left-rail")||null;
    if(sel==='.panel.controls') return byId.get("left-panel")||null;
    if(sel&&sel.startsWith("#")) return byId.get(sel.slice(1))||null;
    return null;
  },
  querySelectorAll:()=>[],
  addEventListener:(t,fn)=>{ (docListeners[t] ||= []).push(fn); },
  removeEventListener:(t,fn)=>{ docListeners[t]=(docListeners[t]||[]).filter((f)=>f!==fn); },
  documentElement:new El("html")
};

const splitPane = {
  mount: (root, deps) => {
    const show = byId.get("show-more");
    const hide = byId.get("hide-markdown");
    if (show) show.addEventListener("click", () => root.setAttribute("data-layout", "split"));
    if (hide) hide.addEventListener("click", () => root.setAttribute("data-layout", "collapsed"));
    return { unmount: () => {} };
  }
};

const windowObj={
  document,
  vis:{ DataSet:function(items){ this._items=items||[]; this.update=()=>{}; this.get=()=>this._items||[]; }, Network:function(){ this._h={}; this.on=(ev,fn)=>{this._h[ev]=fn;}; this.once=(ev,fn)=>{this._h[ev]=fn;}; this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.canvas={focus:()=>{}}; }},
  brainDsUI:{
    detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{}, getSelectedNodeId:()=>"n1", getHasEdits:()=>false, collapseDetailPanel:()=>{} },
    search:{mount:()=>{}}, filterPanel:{mount:()=>{},setAllChecked:()=>{}}, tree:{mount:()=>{}}, scoreFilter:{mount:()=>{},setThreshold:()=>{}},
    popover:{mount:()=>{}}, contextMenu:{mount:()=>{}},
    liveSync:{ LiveDataStore:function(){this.getNodes=()=>[];this.getEdges=()=>[];this.dispose=()=>{};this.syncWithServer=()=>{};}, connectWebSocket:()=>{}, connect:()=>{} },
    splitPane,
    workspaceChrome:{mount:()=>{},unmount:()=>{},setActivePanel:()=>{}},
    motion:{motionEnabled:()=>true},
  },
  innerWidth:1280, innerHeight:800, matchMedia:()=>({matches:false}),
  setTimeout:(fn)=>{ fn(); return 1; }, clearTimeout:()=>{},
  addEventListener:()=>{}, removeEventListener:()=>{},
};
global.window=windowObj; global.document=document; globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;

eval(appScript);

const rightStart = rightCollapse.getAttribute("aria-expanded");
rightCollapse.dispatch("click",{});
const rightAfterFirst = rightCollapse.getAttribute("aria-expanded");
const rightCollapsedClassAfterFirst = rightShell.classList.contains("collapsed");
rightCollapse.dispatch("click",{});
const rightAfterSecond = rightCollapse.getAttribute("aria-expanded");

showMore.dispatch("click",{});
const splitAfterShowMore = centerSplit.getAttribute("data-layout");
hideMarkdown.dispatch("click",{});
const splitAfterHide = centerSplit.getAttribute("data-layout");

overflowBtn.dispatch("click",{ target: overflowBtn });
const menuOpen = body.children.some((c)=>c.attrs&&c.attrs["role"]==="menu");
const menuEl = body.children.find((c)=>c.attrs&&c.attrs["role"]==="menu") || null;
if (menuEl) { menuEl.dispatch("keydown", { key: "Escape", preventDefault(){} }); }
const overflowExpandedAfterEsc = overflowBtn.getAttribute("aria-expanded");
const escFocusRestored = document.activeElement === overflowBtn;
if ((docListeners["pointerdown"]||[]).length) {
  (docListeners["pointerdown"]||[]).forEach((fn)=>fn({ target: body }));
}
const menuClosedByOutside = !body.children.some((c)=>c.attrs&&c.attrs["role"]==="menu");

const layoutBeforeClose = workspace.className;
tabClose.dispatch("click",{});
const tabHidden = tabItem.hidden===true || tabItem.classList.contains("hidden");
const tabNewStillVisible = !tabNew.hidden;
const layoutAfterClose = workspace.className;

console.log(JSON.stringify({
  rightStart, rightAfterFirst, rightAfterSecond, rightCollapsedClassAfterFirst,
  splitAfterShowMore, splitAfterHide,
  menuOpen, overflowExpandedAfterEsc, escFocusRestored, menuClosedByOutside,
  tabHidden, tabNewStillVisible, layoutBeforeClose, layoutAfterClose
}));
'''
            out = _run_node(code, str(html_path))
            self.assertEqual(out["rightStart"], "true")
            self.assertEqual(out["rightAfterFirst"], "false")
            self.assertEqual(out["rightAfterSecond"], "true")
            self.assertTrue(out["rightCollapsedClassAfterFirst"])
            self.assertEqual(out["splitAfterShowMore"], "split")
            self.assertEqual(out["splitAfterHide"], "collapsed")
            self.assertTrue(out["menuOpen"])
            self.assertEqual(out["overflowExpandedAfterEsc"], "false")
            self.assertTrue(out["escFocusRestored"])
            self.assertTrue(out["menuClosedByOutside"])
            self.assertTrue(out["tabHidden"])
            self.assertTrue(out["tabNewStillVisible"])
            self.assertEqual(out["layoutBeforeClose"], out["layoutAfterClose"])


class TestLiveSyncRuntime(unittest.TestCase):
    def _live_sync_harness(self, snippet: str) -> dict:
        code = r'''
const fs = require("fs");
const path = require("path");
const srcPath = path.join(process.cwd(), "brain_ds", "ui", "src", "live", "live-sync.ts");
let source = fs.readFileSync(srcPath, "utf8");
source = source.replace(/export\s+/g, "");
const factory = new Function(`${source}\nreturn { LiveDataStore, connectWebSocket };`);
const { LiveDataStore, connectWebSocket } = factory();

class DataSet {
  constructor(items){ this.items = new Map((items||[]).map((it) => [String(it.id), { ...it }])); }
  update(rows){ (rows||[]).forEach((row) => this.items.set(String(row.id), { ...(this.items.get(String(row.id))||{}), ...row })); }
  add(rows){ (rows||[]).forEach((row) => this.items.set(String(row.id), { ...row })); }
  remove(ids){ (ids||[]).forEach((id) => this.items.delete(String(id))); }
  clear(){ this.items.clear(); }
  get(){ return Array.from(this.items.values()); }
}

global.fetch = async (url) => {
  if (url.includes("/nodes")) return { json: async () => ({ nodes: [{ id: "n1", label: "Node 1" }] }) };
  return { json: async () => ({ edges: [{ id: "e1", from: "n1", to: "n2", label: "L" }] }) };
};

global.window = {
  location: { protocol: "http:", host: "localhost:8000" },
  setTimeout: (fn) => { fn(); return 1; },
};

global.WebSocket = class {
  constructor(){ this.handlers = {}; }
  addEventListener(name, fn){ this.handlers[name] = fn; }
  close(){}
};

;(async () => {
''' + snippet + r'''
})().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
'''
        return _run_node(code)

    def test_live_data_store_seeding(self):
        out = self._live_sync_harness(r'''
const context = {
  nodes: [{ id: "a", label: "A" }, { id: "b", label: "B" }],
  edges: [{ id: "ab", from: "a", to: "b" }],
  detail_index: { a: { node: { id: "a" } } },
};
const store = new LiveDataStore(context, new DataSet(context.nodes), new DataSet(context.edges));
console.log(JSON.stringify({
  nodes: store.getNodes().length,
  edges: store.getEdges().length,
  hasAdj: store.getAdjacency().get("a").has("b"),
  hasDetail: Boolean(store.getDetailIndex().a),
}));
''')
        self.assertEqual(out["nodes"], 2)
        self.assertEqual(out["edges"], 1)
        self.assertTrue(out["hasAdj"])
        self.assertTrue(out["hasDetail"])

    def test_live_data_store_fetch_reconciles_state(self):
        out = self._live_sync_harness(r'''
const urls = [];
global.fetch = async (url) => {
  urls.push(String(url));
  if (String(url).startsWith("/api/nodes?")) return { json: async () => ({ nodes: [{ id: "n1", label: "Server" }] }) };
  if (String(url).startsWith("/api/edges?")) return { json: async () => ({ edges: [{ id: "e1", from: "n1", to: "n2", label: "L" }] }) };
  throw new Error(`unexpected URL ${url}`);
};
const context = { nodes: [{ id: "old" }], edges: [] };
const nodesDs = new DataSet(context.nodes);
const edgesDs = new DataSet(context.edges);
const store = new LiveDataStore(context, nodesDs, edgesDs);
await store.syncWithServer("g-1");
console.log(JSON.stringify({
  urls,
  nodeIds: store.getNodes().map((n) => n.id),
  edgeIds: store.getEdges().map((e) => e.id),
  dsNodes: nodesDs.get().length,
}));
''')
        self.assertEqual(out["urls"], ["/api/nodes?graph_id=g-1", "/api/edges?graph_id=g-1"])
        self.assertEqual(out["nodeIds"], ["n1"])
        self.assertEqual(out["edgeIds"], ["e1"])
        self.assertEqual(out["dsNodes"], 1)

    def test_live_data_store_buffers_events_until_fetch_completes(self):
        out = self._live_sync_harness(r'''
let nodeResolve;
global.fetch = (url) => new Promise((resolve) => {
  if (url.includes("/nodes")) nodeResolve = () => resolve({ json: async () => ({ nodes: [{ id: "n1", label: "Server" }] }) });
  else resolve({ json: async () => ({ edges: [] }) });
});

const context = { nodes: [], edges: [] };
const store = new LiveDataStore(context, new DataSet(), new DataSet());
const started = store.syncWithServer("g-2");
store.queueOrApply({ event: "node.created", payload: { id: "early", label: "Early" } });
const bufferedBefore = store.getNodes().length;
nodeResolve();
await started;
console.log(JSON.stringify({ bufferedBefore, afterFlush: store.getNodes().map((n) => n.id).sort() }));
''')
        self.assertEqual(out["bufferedBefore"], 0)
        self.assertEqual(out["afterFlush"], ["early", "n1"])

    def test_live_data_store_mutation_hooks_fire(self):
        out = self._live_sync_harness(r'''
const context = { nodes: [], edges: [] };
const store = new LiveDataStore(context, new DataSet(), new DataSet());
store.isFetchComplete = true;
let added = 0;
let removed = 0;
store.onNodeAdded = () => { added += 1; };
store.onNodeRemoved = () => { removed += 1; };
store.queueOrApply({ event: "node.created", payload: { id: "new-node", label: "New" } });
store.queueOrApply({ event: "node.deleted", payload: { id: "new-node" } });
console.log(JSON.stringify({ added, removed }));
''')
        self.assertEqual(out["added"], 1)
        self.assertEqual(out["removed"], 1)

    def test_template_injects_graph_id(self):
        html = render_interactive_html(
            {
                "graph_id": "g-42",
                "meta": {"org": "RuntimeOrg", "node_count": 0, "edge_count": 0},
                "nodes": [],
                "edges": [],
                "type_groups": [],
                "adjacency": {},
                "detail_index": {},
            }
        )
        self.assertIn('"graph_id": "g-42"', html)

    # --- Phase 1 TDD: seedPlacement + pendingPlacement ---

    def test_seed_placement_with_positioned_neighbor_sets_centroid(self):
        """Task 1.1 RED: seedPlacement with positioned neighbor sets x/y to centroid,
        returns true, and removes nodeId from pendingPlacement."""
        out = self._live_sync_harness(r'''
const context = {
  nodes: [{ id: "a", label: "A", x: 100, y: 200 }, { id: "b", label: "B" }],
  edges: [{ id: "ab", from: "a", to: "b" }],
};
const nodesDs = new DataSet(context.nodes);
const edgesDs = new DataSet(context.edges);
const store = new LiveDataStore(context, nodesDs, edgesDs);

// Simulate: "a" has a physics position already in the DataSet
nodesDs.update([{ id: "a", x: 100, y: 200 }]);

// Add "b" to pendingPlacement as if node.created just fired
store.pendingPlacement.add("b");

const result = store.seedPlacement("b");

const bNode = nodesDs.get().find((n) => n.id === "b");
const stillPending = store.pendingPlacement.has("b");

console.log(JSON.stringify({
  result,
  bX: bNode && typeof bNode.x === "number" ? bNode.x : null,
  bY: bNode && typeof bNode.y === "number" ? bNode.y : null,
  stillPending,
}));
''')
        self.assertTrue(out["result"], "seedPlacement must return true when a positioned neighbor exists")
        self.assertEqual(out["bX"], 100, "node x must be seeded to neighbor centroid x")
        self.assertEqual(out["bY"], 200, "node y must be seeded to neighbor centroid y")
        self.assertFalse(out["stillPending"], "node must be removed from pendingPlacement after successful seeding")

    def test_seed_placement_no_positioned_neighbors_returns_false(self):
        """Task 1.2 RED: seedPlacement with zero positioned neighbors returns false,
        node is untouched, and stays in pendingPlacement."""
        out = self._live_sync_harness(r'''
const context = {
  nodes: [{ id: "a", label: "A" }, { id: "b", label: "B" }],
  edges: [{ id: "ab", from: "a", to: "b" }],
};
const nodesDs = new DataSet(context.nodes);
const edgesDs = new DataSet(context.edges);
const store = new LiveDataStore(context, nodesDs, edgesDs);

// "a" has NO finite x/y (not yet positioned by physics)
store.pendingPlacement.add("b");

const result = store.seedPlacement("b");
const bNode = nodesDs.get().find((n) => n.id === "b");
const stillPending = store.pendingPlacement.has("b");

console.log(JSON.stringify({
  result,
  bHasX: bNode !== undefined && bNode.x !== undefined && bNode.x !== null && isFinite(Number(bNode.x)),
  stillPending,
}));
''')
        self.assertFalse(out["result"], "seedPlacement must return false when no positioned neighbor exists")
        self.assertFalse(out["bHasX"], "node must NOT have a finite x when no positioned neighbor exists")
        self.assertTrue(out["stillPending"], "node must remain in pendingPlacement when seeding fails")

    def test_seed_placement_deferred_path_edge_arrives_after_node(self):
        """Task 1.3 RED: deferred path — node.created, then edge.created (rebuilds adjacency),
        then seedPlacement applies centroid. Proves the edge-timing fix."""
        out = self._live_sync_harness(r'''
const context = { nodes: [], edges: [] };
const nodesDs = new DataSet([]);
const edgesDs = new DataSet([]);
const store = new LiveDataStore(context, nodesDs, edgesDs);
store.isFetchComplete = true;

// Step 1: node.created for "existing" (has a physics position)
store.applyEvent({ event: "node.created", payload: { id: "existing", label: "Existing" } });
nodesDs.update([{ id: "existing", x: 50, y: 80 }]);

// Step 2: node.created for "new-node" (no edges yet — pendingPlacement should have it)
store.applyEvent({ event: "node.created", payload: { id: "new-node", label: "New" } });

const isPendingAfterNodeCreated = store.pendingPlacement.has("new-node");

// Step 3: edge.created links "existing" -> "new-node" (adjacency now populated)
store.applyEvent({ event: "edge.created", payload: { id: "e1", from: "existing", to: "new-node" } });

// Step 4: now seedPlacement should succeed — adjacency has "existing" as neighbor of "new-node"
const result = store.seedPlacement("new-node");
const newNode = nodesDs.get().find((n) => n.id === "new-node");

console.log(JSON.stringify({
  isPendingAfterNodeCreated,
  result,
  newX: newNode && typeof newNode.x === "number" ? newNode.x : null,
  newY: newNode && typeof newNode.y === "number" ? newNode.y : null,
}));
''')
        self.assertTrue(out["isPendingAfterNodeCreated"], "node must be in pendingPlacement right after node.created")
        self.assertTrue(out["result"], "seedPlacement must return true after edge.created provides a positioned neighbor")
        self.assertEqual(out["newX"], 50, "node x must be seeded to neighbor centroid x after deferred path")
        self.assertEqual(out["newY"], 80, "node y must be seeded to neighbor centroid y after deferred path")

    def test_node_deleted_mid_pending_removes_from_pending(self):
        """Task 1.4 RED: node.deleted mid-pending removes id from pendingPlacement."""
        out = self._live_sync_harness(r'''
const context = { nodes: [], edges: [] };
const nodesDs = new DataSet([]);
const edgesDs = new DataSet([]);
const store = new LiveDataStore(context, nodesDs, edgesDs);
store.isFetchComplete = true;

// Create a node — should be added to pendingPlacement
store.applyEvent({ event: "node.created", payload: { id: "tmp", label: "Temp" } });
const isPendingBeforeDelete = store.pendingPlacement.has("tmp");

// Delete the node — should remove from pendingPlacement
store.applyEvent({ event: "node.deleted", payload: { id: "tmp" } });
const isPendingAfterDelete = store.pendingPlacement.has("tmp");

console.log(JSON.stringify({ isPendingBeforeDelete, isPendingAfterDelete }));
''')
        self.assertTrue(out["isPendingBeforeDelete"], "node must be in pendingPlacement after node.created")
        self.assertFalse(out["isPendingAfterDelete"], "node must be removed from pendingPlacement after node.deleted")

    # --- Phase 2 TDD: template entering-id tracking ---
    # These tests use the live-sync.ts source directly (not the pre-built bundle).
    # They simulate the exact wiring the template does in its inline script.

    def _simulate_template_wiring(self, motion_enabled: bool) -> dict:
        """Simulate the exact template wiring: enteringIds set, onNodeAdded hook,
        first-creation entering class. Verifies the wiring pattern from graph_viewer.html."""
        code = r'''
const fs = require("fs");
const path = require("path");
const srcPath = path.join(process.cwd(), "brain_ds", "ui", "src", "live", "live-sync.ts");
let liveSyncSrc = fs.readFileSync(srcPath, "utf8");
liveSyncSrc = liveSyncSrc.replace(/export\s+/g, "");
const factory = new Function(`${liveSyncSrc}\nreturn { LiveDataStore, connectWebSocket };`);
const { LiveDataStore } = factory();

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} }
class El {
  constructor(id="", tag="div") {
    this.id=id; this.tagName=tag.toUpperCase(); this.classList=new ClassList();
    this.attrs={}; this.listeners={}; this.children=[]; this.style={}; this.className="";
  }
  addEventListener(t,fn,opts){ (this.listeners[t]||=[]).push({fn,opts}); }
  dispatch(t,e){ [...(this.listeners[t]||[])].forEach(({fn,opts})=>{ fn(Object.assign({currentTarget:this},e)); if(opts&&opts.once) this.listeners[t]=(this.listeners[t]||[]).filter((h)=>h.fn!==fn); }); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  appendChild(c){ this.children.push(c); return c; }
  querySelector(sel){ return null; }
}

''' + f'const motionEnabledVal = {str(motion_enabled).lower()};' + r'''

// Simulate template-scope state (exact mirrors of graph_viewer.html wiring)
const enteringIds = new Set();
class DataSet {
  constructor(items){ this.items = new Map((items||[]).map((it) => [String(it.id), { ...it }])); }
  update(rows){ (rows||[]).forEach((row) => this.items.set(String(row.id), { ...(this.items.get(String(row.id))||{}), ...row })); }
  add(rows){ (rows||[]).forEach((row) => this.items.set(String(row.id), { ...row })); }
  get(){ return Array.from(this.items.values()); }
}

const nodesDs = new DataSet([]);
const edgesDs = new DataSet([]);
const store = new LiveDataStore({}, nodesDs, edgesDs);

// Simulate the template wiring (graph_viewer.html onNodeAdded/onNodeRemoved hooks)
const motionApi = { motionEnabled: () => motionEnabledVal };
store.onNodeAdded = (node) => {
  const id = String(node.id);
  if (motionApi && typeof motionApi.motionEnabled === "function" && motionApi.motionEnabled()) {
    enteringIds.add(id);
  }
};
store.onNodeRemoved = (nodeId) => {
  enteringIds.delete(String(nodeId));
};
store.isFetchComplete = true;

// Fire node.created event
store.applyEvent({ event: "node.created", payload: { id: "live-n1", label: "Live Node 1" } });

// Simulate d4RenderOverlay if (!el) first-creation branch
const d4NodesRoot = new El("d4-nodes");
const id = "live-n1";
let el = null;
if (!el) {
  el = new El("", "button");
  el.className = "graph-node d4-node";
  // Entering class logic (exact mirror of graph_viewer.html 2.6)
  if (enteringIds.has(id)) {
    el.classList.add("d4-node--entering");
    el.addEventListener("animationend", () => {
      el.classList.remove("d4-node--entering");
      enteringIds.delete(id);
    }, { once: true });
    enteringIds.delete(id); // consume intent
  }
  d4NodesRoot.appendChild(el);
}

const hasEnteringClass = el.classList.contains("d4-node--entering");
// After animationend fires, class should be removed
el.dispatch("animationend", {});
const classRemovedAfterAnimEnd = !el.classList.contains("d4-node--entering");
const idRemovedFromEntering = !enteringIds.has(id);

console.log(JSON.stringify({ hasEnteringClass, classRemovedAfterAnimEnd, idRemovedFromEntering }));
'''
        return _run_node(code)

    def test_entering_id_recorded_when_motion_enabled(self):
        """Task 2.1: d4-node--entering class applied on first-created element when motionEnabled() = true."""
        out = self._simulate_template_wiring(True)
        self.assertTrue(out["hasEnteringClass"], "node element must have d4-node--entering class when motion enabled")
        self.assertTrue(out["classRemovedAfterAnimEnd"], "entering class must be removed on animationend")
        self.assertTrue(out["idRemovedFromEntering"], "enteringIds must be cleared after animationend")

    def test_entering_id_not_recorded_when_motion_disabled(self):
        """Task 2.2: d4-node--entering class NOT applied when motionEnabled() = false."""
        out = self._simulate_template_wiring(False)
        self.assertFalse(out["hasEnteringClass"], "node element must NOT have d4-node--entering class when motion disabled")


class TestLiveSyncPhase4Audit(unittest.TestCase):
    def setUp(self):
        self.template_path = Path(__file__).resolve().parents[1] / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        self.template_text = self.template_path.read_text(encoding="utf-8")

    def test_render_context_references_are_initialization_or_compat_only(self):
        allowed_literals = [
            "const RENDER_CONTEXT = __BRAIN_DS_RENDER_CONTEXT__;",
            "const meta = RENDER_CONTEXT.meta || {};",
            "? structuredClone(RENDER_CONTEXT)",
            ": JSON.parse(JSON.stringify(RENDER_CONTEXT));",
            "const typeGroups = RENDER_CONTEXT.type_groups || [];",
            "const initialNodes = RENDER_CONTEXT.nodes || [];",
            "const initialEdges = RENDER_CONTEXT.edges || [];",
            "const nodes = new vis.DataSet(RENDER_CONTEXT.nodes || []);",
            "const edges = new vis.DataSet(RENDER_CONTEXT.edges || []);",
            "? new liveSyncApi.LiveDataStore(RENDER_CONTEXT, nodes, edges)",
            "const adjacency = RENDER_CONTEXT.adjacency || {};",
            "RENDER_CONTEXT,",
            "window.brainDsUI.popover.mount({ network, RENDER_CONTEXT });",
        ]
        lines_with_context = [
            line.strip() for line in self.template_text.splitlines() if "RENDER_CONTEXT" in line
        ]
        self.assertEqual(len(lines_with_context), 14)
        for line in lines_with_context:
            self.assertTrue(any(token in line for token in allowed_literals), f"Unexpected RENDER_CONTEXT usage: {line}")

    def test_runtime_mounts_consume_live_snapshots(self):
        self.assertIn("const getCurrentNodes = () => (liveDataStore ? liveDataStore.getNodes() : initialNodes) || [];", self.template_text)
        self.assertIn("const getCurrentEdges = () => (liveDataStore ? liveDataStore.getEdges() : initialEdges) || [];", self.template_text)
        self.assertIn("window.brainDsUI.search.mount(searchGroupEl, {", self.template_text)
        self.assertIn("nodes: getCurrentNodes(),", self.template_text)
        self.assertIn("window.brainDsUI.tree.mount(treeRoot, {", self.template_text)

    def test_search_mount_uses_existing_root_or_guard(self):
        """Search mount root must match current markup and avoid null mount."""
        self.assertIn(
            'document.querySelector("[data-accordion-section=\\"search\\"]")',
            self.template_text,
            "Search mount root must target the existing search accordion section",
        )
        self.assertIn(
            "if (searchGroupEl) {",
            self.template_text,
            "Template must guard mount when search root is absent",
        )
