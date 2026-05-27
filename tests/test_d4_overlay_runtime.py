import re
import tempfile
import unittest
from pathlib import Path

from brain_ds.ui.template_renderer import render_interactive_html
from tests.test_ui_runtime_behavior import _run_node


class TestD4OverlayRuntimeContracts(unittest.TestCase):
    def _render_html_path(self) -> Path:
        context = {
            "meta": {"org": "RuntimeOrg", "node_count": 3, "edge_count": 2, "generated_at": ""},
            "nodes": [
                {"id": "a", "label": "A", "type": "Department", "component_id": 1, "score": 0.9},
                {"id": "b", "label": "B", "type": "Role", "component_id": 2, "score": 0.7},
                {"id": "c", "label": "C", "type": "Team", "component_id": 3, "score": 0.5},
            ],
            "edges": [
                {"id": "e1", "from": "a", "to": "b", "score": 0.8},
                {"id": "e2", "from": "b", "to": "c", "score": 0.6},
            ],
            "type_groups": [],
            "adjacency": {"a": ["b"], "b": ["a", "c"], "c": ["b"]},
            "detail_index": {},
        }
        html = render_interactive_html(context)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        html_path = Path(tmp.name) / "runtime-d4.html"
        html_path.write_text(html, encoding="utf-8")
        return html_path

    def _run_overlay_case(self, extra_js: str) -> dict:
        html_path = self._render_html_path()
        code = r'''
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appScript = scripts[scripts.length - 1];

class ClassList { constructor(){ this.s=new Set(); } add(c){this.s.add(c);} remove(c){this.s.delete(c);} contains(c){return this.s.has(c);} toggle(c,f){ if(f===undefined){ this.s.has(c)?this.s.delete(c):this.s.add(c);} else {f?this.s.add(c):this.s.delete(c);} } }
class El {
  constructor(id="", tag="div"){
    const styleStore = {};
    this.id=id; this.tagName=tag.toUpperCase(); this.children=[]; this.classList=new ClassList(); this.attrs={}; this.listeners={}; this.style={ setProperty:(k,v)=>{ styleStore[k]=String(v); this.style[k]=String(v); }, getPropertyValue:(k)=>styleStore[k] || "" }; this.dataset={}; this.parentNode=null;
    this.hidden=false; this.textContent=""; this.innerHTML=""; this.className=""; this.tabIndex=-1;
  }
  appendChild(c){ c.parentNode=this; this.children.push(c); return c; }
  insertBefore(c, ref){ c.parentNode=this; const idx=this.children.indexOf(ref); if (idx >= 0) this.children.splice(idx,0,c); else this.children.push(c); return c; }
  removeChild(c){ this.children = this.children.filter((x)=>x!==c); c.parentNode=null; }
  addEventListener(t,fn){ (this.listeners[t] ||= []).push(fn); }
  dispatch(t,e){ (this.listeners[t]||[]).forEach((fn)=>fn(e||{})); }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  removeAttribute(k){ delete this.attrs[k]; }
  focus(){ document.activeElement=this; }
  closest(){ return document.body; }
  querySelector(sel){
    if (sel === ".node-label") return this.children.find((c)=>c.className==="node-label") || null;
    if (sel && sel.startsWith("#")) return document.getElementById(sel.slice(1));
    return null;
  }
  querySelectorAll(){ return this.children; }
}

const ids=["org-name","org-meta","org-ts","network","detail-panel","detail-collapse","detail-close","score-badge","score-threshold-slider","theme-toggle","detail-panel-backdrop","viewer-loading","viewer-empty","empty-reset-filters","viewer-live-region","detail-body","search-results","node-search","type-filters","legend","show-all","hide-all","toggle-hierarchical","toggle-physics","zoom-fit","edit-toggle","export-json","search-group","controls","center-split","d4-nodes","d4-edges","tree-filter-chip","workspace-view-org","workspace-view-nodes","workspace-view-edges"];
const byId=new Map(ids.map((id)=>[id,new El(id)]));
const body = new El("body","body");
body.appendChild(byId.get("network"));
body.appendChild(byId.get("center-split"));
byId.get("center-split").appendChild(byId.get("d4-edges"));
byId.get("center-split").appendChild(byId.get("d4-nodes"));
byId.get("search-group").appendChild(byId.get("node-search"));
byId.get("search-group").appendChild(byId.get("search-results"));

const document={
  activeElement:null,
  body,
  getElementById:(id)=>byId.get(id)||null,
  querySelector:(sel)=>{ if(sel===".search-group") return byId.get("search-group"); if(sel===".controls") return byId.get("controls"); if (sel && sel.startsWith("#")) return byId.get(sel.slice(1))||null; return null; },
  createElement:(tag)=>new El("",tag),
  createElementNS:(ns,tag)=>new El("",tag),
  createTextNode:(txt)=>{ const e=new El(); e.textContent=String(txt); return e; },
  addEventListener:()=>{}, removeEventListener:()=>{}, documentElement:new El("html","html")
};

const rafQueue=[];
const networkHandlers={};
let networkCount=0;
const windowObj={
  document,
  vis:{
    DataSet:function(items){ this._items=[...(items||[])]; this.get=()=>this._items; this.update=()=>{}; this.on=()=>{}; },
    Network:function(container,data){
      networkCount += 1;
      this.canvas={focus:()=>{}};
      this.viewport={scale:1,tx:0,ty:0};
      this.data={nodes:{get:()=>{
        const ns=(data && data.nodes && data.nodes._items) ? data.nodes._items : [];
        return ns.map((n,idx)=>({ ...n, x: (idx+1)*50, y: (idx+1)*40 }));
      }}};
      this.on=(ev,fn)=>{ networkHandlers[ev]=fn; };
      this.once=(ev,fn)=>{ networkHandlers[ev]=fn; };
      this.off=()=>{}; this.fit=()=>{}; this.setOptions=()=>{}; this.redraw=()=>{}; this.selectNodes=()=>{};
      this._worldToScreen=(x,y)=>({x,y});
    }
  },
  brainDsUI:{ detailPanel:{ mount:()=>{}, setEditMode:()=>{}, setSelectedNodeId:()=>{}, renderDetailPanel:()=>{} }, search:{ mount:()=>{} }, filterPanel:{ mount:()=>{}, setAllChecked:()=>{} }, scoreFilter:{ mount:()=>{}, setThreshold:()=>{} }, popover:{ mount:()=>{} }, contextMenu:{ mount:()=>{} }, liveSync:null, motion:{ motionEnabled:()=>true } },
  innerWidth:1200,
  matchMedia:()=>({matches:false, addEventListener:()=>{}, removeEventListener:()=>{}}),
  requestAnimationFrame:(cb)=>{ rafQueue.push(cb); return rafQueue.length; },
  setTimeout:(fn)=>{ fn(); return 1; },
  clearTimeout:()=>{},
  addEventListener:()=>{},
  removeEventListener:()=>{}
};
global.window=windowObj; global.document=document; globalThis.window=windowObj; globalThis.document=document; globalThis.vis=windowObj.vis;

eval(appScript);
if (rafQueue.length) { const cb = rafQueue.shift(); cb(); }

const emit = (name, payload) => { if (networkHandlers[name]) networkHandlers[name](payload || {}); };
const stateFor = (nodeId) => {
  const node = byId.get("d4-nodes").children.find((n)=>n.dataset && n.dataset.id===String(nodeId));
  return node ? node.dataset.state : null;
};
const firstEdge = byId.get("d4-edges").children[0] || null;
const secondEdge = byId.get("d4-edges").children[1] || null;

__EXTRA_JS__
'''.replace("__EXTRA_JS__", extra_js)
        return _run_node(code, str(html_path))

    def test_idle_and_single_network_contract(self):
        out = self._run_overlay_case(
            """
const canvas = byId.get("center-split");
console.log(JSON.stringify({
  networkCount,
  hasHover: canvas.getAttribute("data-has-hover"),
  hasSelection: canvas.getAttribute("data-has-selection"),
  nodeCount: byId.get("d4-nodes").children.length,
  edgeCount: byId.get("d4-edges").children.length
}));
"""
        )
        self.assertEqual(out["networkCount"], 1)
        self.assertEqual(out["hasHover"], "false")
        self.assertEqual(out["hasSelection"], "false")
        self.assertGreaterEqual(out["nodeCount"], 3)
        self.assertGreaterEqual(out["edgeCount"], 2)

    def test_hover_selected_and_edge_emphasis_contract(self):
        out = self._run_overlay_case(
            """
emit("hoverNode", { node: "b" });
emit("selectNode", { nodes: ["b"] });
const canvas = byId.get("center-split");
console.log(JSON.stringify({
  hoverTarget: stateFor("b"),
  relatedA: stateFor("a"),
  relatedC: stateFor("c"),
  hasSelection: canvas.getAttribute("data-has-selection"),
  edgeEmphasis: firstEdge && firstEdge.getAttribute("data-emphasis"),
  edgeRelated: firstEdge && firstEdge.getAttribute("data-related")
}));
"""
        )
        self.assertEqual(out["hoverTarget"], "selected-target")
        self.assertEqual(out["relatedA"], "selected-related")
        self.assertEqual(out["relatedC"], "selected-related")
        self.assertEqual(out["hasSelection"], "true")
        self.assertEqual(out["edgeEmphasis"], "selected")
        self.assertEqual(out["edgeRelated"], "true")

    def test_blur_and_deselect_return_idle(self):
        out = self._run_overlay_case(
            """
emit("hoverNode", { node: "a" });
emit("blurNode", {});
emit("selectNode", { nodes: ["a"] });
emit("deselectNode", {});
const canvas = byId.get("center-split");
console.log(JSON.stringify({
  stateA: stateFor("a"),
  stateB: stateFor("b"),
  hasHover: canvas.getAttribute("data-has-hover"),
  hasSelection: canvas.getAttribute("data-has-selection")
}));
"""
        )
        self.assertEqual(out["stateA"], "default")
        self.assertEqual(out["stateB"], "default")
        self.assertEqual(out["hasHover"], "false")
        self.assertEqual(out["hasSelection"], "false")

    def test_node_color_vars_applied(self):
        out = self._run_overlay_case(
            """
const nodeA = byId.get("d4-nodes").children.find((n)=>n.dataset && n.dataset.id==="a");
console.log(JSON.stringify({
  nodeColor: nodeA && nodeA.style["--node-color"],
  nodeMuted: nodeA && nodeA.style["--node-color-muted"]
}));
"""
        )
        self.assertTrue(str(out["nodeColor"]).startswith("#"))
        self.assertIn("rgba(", str(out["nodeMuted"]))

    def test_dimmed_node_path_uses_muted_token_contract(self):
        out = self._run_overlay_case(
            """
emit("hoverNode", { node: "a" });
const canvas = byId.get("center-split");
const nodeC = byId.get("d4-nodes").children.find((n)=>n.dataset && n.dataset.id==="c");
console.log(JSON.stringify({
  hasHover: canvas.getAttribute("data-has-hover"),
  stateC: stateFor("c"),
  nodeCMuted: nodeC && nodeC.style["--node-color-muted"]
}));
"""
        )
        self.assertEqual(out["hasHover"], "true")
        self.assertEqual(out["stateC"], "default")
        self.assertRegex(str(out["nodeCMuted"]), r"rgba\(.+\)")

    def test_unrelated_edge_is_explicitly_dimmed_on_selection(self):
        out = self._run_overlay_case(
            """
emit("selectNode", { nodes: ["a"] });
console.log(JSON.stringify({
  firstRelated: firstEdge && firstEdge.getAttribute("data-related"),
  firstEmphasis: firstEdge && firstEdge.getAttribute("data-emphasis"),
  secondRelated: secondEdge && secondEdge.getAttribute("data-related"),
  secondEmphasis: (secondEdge && secondEdge.getAttribute("data-emphasis")) || null
}));
"""
        )
        self.assertEqual(out["firstRelated"], "true")
        self.assertEqual(out["firstEmphasis"], "selected")
        self.assertEqual(out["secondRelated"], "false")
        self.assertIsNone(out["secondEmphasis"])

    def test_reduced_motion_helper_runtime(self):
        code = r'''
const fs = require("fs");
const path = require("path");
const bundle = fs.readFileSync(path.join(process.cwd(), "brain_ds", "ui", "assets", "viewer.bundle.js"), "utf8");
global.window = { matchMedia: () => ({ matches: true, addEventListener:()=>{}, removeEventListener:()=>{} }) };
global.document = {};
globalThis.window = global.window;
globalThis.document = global.document;
eval(bundle);
console.log(JSON.stringify({ motionEnabled: window.brainDsUI.motion.motionEnabled() }));
'''
        out = _run_node(code)
        self.assertFalse(out["motionEnabled"])

    def test_bundle_source_drift_guard_contract_strings(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        bundle_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets" / "viewer.bundle.js"
        template = template_path.read_text(encoding="utf-8")
        bundle = bundle_path.read_text(encoding="utf-8")
        expected = [
            "data-has-hover",
            "data-has-selection",
            "hover-target",
            "selected-target",
        ]
        for token in expected:
            self.assertRegex(template, re.escape(token))
            self.assertRegex(bundle, re.escape(token))
        self.assertRegex(template, r"data-emphasis")
        self.assertRegex(bundle, r"data-emphasis")
        self.assertRegex(bundle, r"data-related")

    def test_reduced_motion_css_disables_transitions_and_animations_contract(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        bundle_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets" / "viewer.bundle.js"
        template = template_path.read_text(encoding="utf-8")
        bundle = bundle_path.read_text(encoding="utf-8")

        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*reduce\)")
        self.assertRegex(template, r"transition:\s*none")
        self.assertRegex(template, r"animation:\s*none")
        self.assertRegex(bundle, r"prefers-reduced-motion")

    def test_template_reuses_existing_network_and_modularizes_d4_overlay_contract(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template = template_path.read_text(encoding="utf-8")

        self.assertRegex(template, r"window\.brainDsUI\s*&&\s*window\.brainDsUI\.network")
        self.assertRegex(template, r"const\s+network\s*=\s*existingNetwork\s*\|\|\s*new\s+vis\.Network")
        self.assertRegex(template, r"window\.brainDsUI\s*&&\s*window\.brainDsUI\.rendererD4")
        self.assertRegex(template, r"rendererD4\.mount\s*\(")

    def test_template_click_handler_skips_refocus_for_already_selected_node(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template = template_path.read_text(encoding="utf-8")

        click_guard_pattern = (
            r"network\.on\(\"click\",\s*\(params\)\s*=>\s*\{[\s\S]*?"
            r"const\s+clickedNodeId\s*=\s*params\.nodes\[0\];[\s\S]*?"
            r"if\s*\(clickedNodeId\s*!==\s*selectedNodeId\)\s*\{[\s\S]*?"
            r"focusNode\(clickedNodeId\);"
        )
        self.assertRegex(template, click_guard_pattern)

        # Contract edge-case: deselect click (empty canvas click) still resets highlight state.
        self.assertRegex(template, r"else\s+if\s*\(selectedNodeId\)\s*\{[\s\S]*?resetHighlight\(\);")

    def test_popover_has_tooltip_a11y_contract(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template = template_path.read_text(encoding="utf-8")

        self.assertRegex(template, r"pop\.setAttribute\(\"role\",\s*\"tooltip\"\)")
        self.assertRegex(template, r"pop\.setAttribute\(\"aria-label\",\s*\"Node details\"\)")

    def test_popover_escape_dismiss_contract(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template = template_path.read_text(encoding="utf-8")

        self.assertRegex(
            template,
            r"document\.addEventListener\(\s*\"keydown\",\s*\(event\)\s*=>\s*\{[\s\S]*?"
            r"event\.key\s*===\s*\"Escape\"[\s\S]*?d4HidePopover\(\)",
        )

    def test_d4_motion_is_gated_by_no_preference_contract(self):
        template_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "templates" / "graph_viewer.html"
        template = template_path.read_text(encoding="utf-8")

        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*no-preference\)")
        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*no-preference\)[\s\S]*?\.d4-edge[\s\S]*?transition:")
        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*no-preference\)[\s\S]*?animation:\s*node-hover-breathe")
        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*no-preference\)[\s\S]*?animation:\s*d4-popover-reveal")
        self.assertRegex(template, r"@media\s*\(prefers-reduced-motion:\s*no-preference\)[\s\S]*?animation:\s*node-entrance")

    def test_bundle_matches_phase4_motion_and_popover_contracts(self):
        bundle_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "assets" / "viewer.bundle.js"
        bundle = bundle_path.read_text(encoding="utf-8")

        # Bundle parity guards for Phase 4 contracts (stale bundle must fail this test).
        self.assertRegex(bundle, r"prefers-reduced-motion")
        self.assertRegex(bundle, r"tooltip")
        self.assertRegex(bundle, r"Node details")
        self.assertRegex(bundle, r"Escape")

    def test_renderer_d4_resolves_label_with_generated_data_fallbacks_contract(self):
        renderer_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "renderer-d4.ts"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertRegex(source, r"resolveNodeLabel")
        self.assertRegex(source, r"node\.label")
        self.assertRegex(source, r"node\.title")
        self.assertRegex(source, r"node\.name")
        self.assertRegex(source, r"node\.id")

    def test_renderer_d4_sets_meaningful_node_aria_label_contract(self):
        renderer_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "renderer-d4.ts"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertRegex(source, r"resolveNodeAriaLabel")
        self.assertRegex(source, r"score")
        self.assertRegex(source, r"type")
        self.assertRegex(source, r"aria-label")

    def test_renderer_d4_click_activation_notifies_detail_path_contract(self):
        renderer_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "renderer-d4.ts"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertRegex(source, r"onNodeActivate")
        self.assertRegex(source, r"addEventListener\('click'|addEventListener\(\"click\"")
        self.assertRegex(source, r"network\.selectNodes")
