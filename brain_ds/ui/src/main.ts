import './main.css';
import './renderer';
import * as detailPanel from './panels/detail-panel';
import * as search from './panels/search';
import * as filterPanel from './panels/filter-panel';
import * as tree from './panels/tree';
import * as splitPane from './panels/split-pane';
import * as scoreFilter from './interactions/score-filter';
import * as contextMenu from './interactions/context-menu';
import * as popover from './interactions/popover';
import * as liveSync from './live/live-sync';
import { motionEnabled } from './motion/motion';
import * as workspaceChrome from './workspace-chrome';
import * as rendererD4 from './renderer-d4';

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
      tree: typeof tree;
      splitPane: typeof splitPane;
      scoreFilter: typeof scoreFilter;
      contextMenu: typeof contextMenu;
      popover: typeof popover;
      liveSync: typeof liveSync;
      motion: { motionEnabled: typeof motionEnabled };
      workspaceChrome: typeof workspaceChrome;
      rendererD4: typeof rendererD4;
    };
  }
}

// Expose panel modules on window.brainDsUI so the template inline script
// can delegate DOM construction to them.
// PR 3: detailPanel added. PR 4: search added. PR 5: filterPanel, scoreFilter added.
// PR 6: contextMenu, popover added. PR 7: workspaceChrome added (Slice 1 P0).
window.brainDsUI = {
  detailPanel,
  network: null,
  search,
  filterPanel,
  tree,
  splitPane,
  scoreFilter,
  contextMenu,
  popover,
  liveSync,
  motion: { motionEnabled },
  workspaceChrome,
  rendererD4,
};

// Network ownership is template-driven (`graph_viewer.html`) to avoid
// duplicate `vis.Network` instances when inline runtime wiring is active.
