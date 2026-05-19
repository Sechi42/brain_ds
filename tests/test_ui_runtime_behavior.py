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
const ids = ["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty-state","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls"]; 
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

const ids=["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty-state","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls","detail-title","detail-meta"];
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
  "viewer-empty-state","empty-reset-filters","viewer-live-region","detail-body","search-results",
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

const emptyStateEl = byId.get("viewer-empty-state");
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
  constructor(tag="div", id=""){ this.tagName=tag.toUpperCase(); this.id=id; this.children=[]; this.parentNode=null; this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.textContent=""; this.innerHTML=""; this.style={}; this.hidden=false; this.value=""; this.disabled=false; }
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
