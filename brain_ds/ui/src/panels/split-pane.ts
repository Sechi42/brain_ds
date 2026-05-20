// @ts-nocheck

import { renderMarkdown } from './markdown-mini';

export function mount(root: HTMLElement, deps: { getMarkdown?: () => string } = {}): { unmount: () => void } {
  if (!root) return { unmount: () => {} };
  const showBtn = document.getElementById('show-more');
  const hideBtn = document.getElementById('hide-markdown');
  const reader = document.getElementById('markdown-reader');

  const show = () => {
    root.setAttribute('data-layout', 'split');
    if (reader) {
      const raw = typeof deps.getMarkdown === 'function' ? deps.getMarkdown() : '';
      reader.innerHTML = raw ? renderMarkdown(raw) : '<p>No content available</p>';
    }
  };

  const hide = () => {
    root.setAttribute('data-layout', 'collapsed');
  };

  showBtn?.addEventListener('click', show);
  hideBtn?.addEventListener('click', hide);

  return {
    unmount: () => {
      showBtn?.removeEventListener('click', show);
      hideBtn?.removeEventListener('click', hide);
    },
  };
}
