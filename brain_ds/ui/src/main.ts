import './main.css';
import './renderer';
import * as detailPanel from './panels/detail-panel';
import * as search from './panels/search';
import * as filterPanel from './panels/filter-panel';
import * as typeColor from './type-color';
import * as tree from './panels/tree';
import * as splitPane from './panels/split-pane';
import * as scoreFilter from './interactions/score-filter';
import * as contextMenu from './interactions/context-menu';
import * as popover from './interactions/popover';
import * as liveSync from './live/live-sync';
import { motionEnabled } from './motion/motion';
import * as workspaceChrome from './workspace-chrome';
import * as workspaceState from './workspace-state';
import * as rendererD4 from './renderer-d4';
import * as tabs from './tabs';
import * as brdPanel from './panels/brd-panel';
import * as secretPanel from './panels/secret-panel';
import * as pipelinePanel from './panels/pipeline-panel';
import * as aiActionsPanel from './panels/ai-actions-panel';

declare global {
  interface Window {
    vis?: {
      DataSet: new (items: unknown[]) => unknown;
      Network: new (container: HTMLElement, data: { nodes: unknown; edges: unknown }, options: Record<string, unknown>) => unknown;
    };
    brainDsUI?: {
      detailPanel: typeof detailPanel;
      graphId?: string;
      network?: unknown;
      search: typeof search;
       filterPanel: typeof filterPanel;
       typeColor: typeof typeColor;
      tree: typeof tree;
    splitPane: typeof splitPane;
    scoreFilter: typeof scoreFilter;
      bundleRevision?: string;
      contextMenu: typeof contextMenu;
      popover: typeof popover;
      liveSync: typeof liveSync;
      motion: { motionEnabled: typeof motionEnabled };
      workspaceChrome: typeof workspaceChrome;
      workspaceState: typeof workspaceState;
      rendererD4: typeof rendererD4;
      tabs: typeof tabs;
      brdPanel: typeof brdPanel;
      secretPanel: typeof secretPanel;
      pipelinePanel: typeof pipelinePanel;
      aiActionsPanel: typeof aiActionsPanel;
  };
  }
}

// Expose panel modules on window.brainDsUI so the template inline script
// can delegate DOM construction to them.
// PR 3: detailPanel added. PR 4: search added. PR 5: filterPanel, scoreFilter added.
// PR 6: contextMenu, popover added. PR 7: workspaceChrome added (Slice 1 P0).
// PR 8: tabs (functional graph tabs) and brdPanel added.
window.brainDsUI = {
  detailPanel,
  network: null,
  search,
  filterPanel,
  typeColor,
  tree,
  splitPane,
  scoreFilter,
  bundleRevision: "chrome-consistency-20260714",
  contextMenu,
  popover,
  liveSync,
  motion: { motionEnabled },
  workspaceChrome,
  workspaceState,
  rendererD4,
  tabs,
  brdPanel,
  secretPanel,
  pipelinePanel,
  aiActionsPanel,
};

// Network ownership is template-driven (`graph_viewer.html`) to avoid
// duplicate `vis.Network` instances when inline runtime wiring is active.
