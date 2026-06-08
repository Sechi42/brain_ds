// @ts-nocheck

import { renderMarkdown } from './markdown-mini';

export function mount(root: HTMLElement, deps: { getMarkdown?: () => string } = {}): { unmount: () => void } {
  if (!root) return { unmount: () => {} };
  const showBtn = document.getElementById('show-more');
  const hideBtn = document.getElementById('hide-markdown');
  const reader = document.getElementById('markdown-reader');
  let previousLayout = root.getAttribute('data-layout') || 'collapsed';
  let lastTrigger: HTMLElement | null = null;

  const show = () => {
    previousLayout = root.getAttribute('data-layout') || 'collapsed';
    root.setAttribute('data-layout', 'reader');
    if (reader) {
      const raw = typeof deps.getMarkdown === 'function' ? deps.getMarkdown() : '';
      reader.innerHTML = raw ? renderMarkdown(raw) : '<p>No content available</p>';
      reader.setAttribute('tabindex', '-1');
      reader.scrollTop = 0;
      if (typeof (reader as HTMLElement).focus === 'function') {
        (reader as HTMLElement).focus();
      }
    }
  };

  const hide = () => {
    root.setAttribute('data-layout', previousLayout);
    if (lastTrigger && typeof lastTrigger.focus === 'function') {
      lastTrigger.focus();
    }
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && root.getAttribute('data-layout') === 'reader') {
      event.preventDefault();
      hide();
    }
  };

  const onShowClick = (event: Event) => {
    lastTrigger = (event.currentTarget as HTMLElement) || showBtn as HTMLElement;
    show();
  };

  showBtn?.addEventListener('click', onShowClick);
  hideBtn?.addEventListener('click', hide);
  document.addEventListener('keydown', onKeydown);

  return {
    unmount: () => {
      showBtn?.removeEventListener('click', onShowClick);
      hideBtn?.removeEventListener('click', hide);
      document.removeEventListener('keydown', onKeydown);
    },
  };
}
