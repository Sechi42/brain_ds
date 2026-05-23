import './main.css';
import './renderer';
import * as rendererDom from './renderer-dom';
import * as detailPanel from './panels/detail-panel';
import * as search from './panels/search';
import * as filterPanel from './panels/filter-panel';
import * as tree from './panels/tree';
import * as splitPane from './panels/split-pane';
import * as scoreFilter from './interactions/score-filter';
import * as contextMenu from './interactions/context-menu';
import * as popover from './interactions/popover';

declare global {
  interface Window {
    vis?: {
      DataSet: new (items: unknown[]) => unknown;
      Network: new (container: HTMLElement, data: { nodes: unknown; edges: unknown }, options: Record<string, unknown>) => unknown;
    };
    brainDsUI?: {
      detailPanel: typeof detailPanel;
      network?: unknown;
      search: typeof search;
      filterPanel: typeof filterPanel;
      tree: typeof tree;
      splitPane: typeof splitPane;
      scoreFilter: typeof scoreFilter;
      contextMenu: typeof contextMenu;
      popover: typeof popover;
    };
  }
}

// Expose panel modules on window.brainDsUI so the template inline script
// can delegate DOM construction to them.
// PR 3: detailPanel added. PR 4: search added. PR 5: filterPanel, scoreFilter added.
// PR 6: contextMenu, popover added.
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
};

(() => {
  const context = (globalThis as Record<string, unknown>).RENDER_CONTEXT as Record<string, unknown> | undefined;
  if (!context || !window.vis) return;

  const container = document.getElementById('network');
  const nodesRoot = document.getElementById('d4-nodes');
  const edgesRoot = document.getElementById('d4-edges') as SVGSVGElement | null;
  const canvasContainer = document.querySelector('.canvas-container') as HTMLElement | null;
  if (!container || !nodesRoot || !edgesRoot || !canvasContainer) return;

  const RENDER_CONTEXT = context as {
    nodes: unknown[];
    edges: unknown[];
  };

  const nodes = new vis.DataSet(RENDER_CONTEXT.nodes || []);
  const edges = new vis.DataSet(RENDER_CONTEXT.edges || []);
  const network = new vis.Network(container, { nodes, edges }, {
    layout: { hierarchical: { enabled: true, direction: 'UD' } },
    interaction: { hover: true, navigationButtons: true, keyboard: true },
    physics: { enabled: false },
    edges: { arrows: { to: { enabled: true, scaleFactor: 0.7 } }, smooth: { enabled: true, type: 'cubicBezier' } },
    nodes: { shape: 'dot', size: 18 },
  });

  rendererDom.mount({
    network,
    dataset: nodes,
    edgesDataset: edges,
    nodesRoot,
    edgesRoot,
    container: canvasContainer,
  });
})();
