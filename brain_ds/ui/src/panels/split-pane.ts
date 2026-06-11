// @ts-nocheck

import { renderMarkdown } from './markdown-mini';

export function mount(
  root: HTMLElement,
  deps: { getMarkdown?: () => string; saveMarkdown?: (markdown: string) => Promise<boolean> } = {},
): { unmount: () => void } {
  if (!root) return { unmount: () => {} };
  const showBtn = document.getElementById('show-more');
  const hideBtn = document.getElementById('hide-markdown');
  const reader = document.getElementById('markdown-reader');
  let previousLayout = root.getAttribute('data-layout') || 'collapsed';
  let lastTrigger: HTMLElement | null = null;
  let editing = false;

  const makeButton = (id: string, label: string, onClick: () => void): HTMLButtonElement => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = id;
    btn.className = 'pill-btn btn-outline reader-btn';
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
  };

  const renderPreview = () => {
    if (!reader) return;
    editing = false;
    const raw = typeof deps.getMarkdown === 'function' ? deps.getMarkdown() : '';
    reader.innerHTML = '';

    const toolbar = document.createElement('div');
    toolbar.className = 'reader-toolbar';
    if (typeof deps.saveMarkdown === 'function' && raw) {
      toolbar.appendChild(makeButton('reader-edit', 'Editar', () => renderEditor(raw)));
    }
    if (toolbar.childNodes.length) reader.appendChild(toolbar);

    const content = document.createElement('div');
    content.className = 'reader-content';
    content.innerHTML = raw ? renderMarkdown(raw) : '<p>No content available</p>';
    reader.appendChild(content);
  };

  const renderEditor = (raw: string) => {
    if (!reader) return;
    editing = true;
    reader.innerHTML = '';

    const toolbar = document.createElement('div');
    toolbar.className = 'reader-toolbar';
    const status = document.createElement('span');
    status.className = 'reader-status';
    status.setAttribute('role', 'status');

    const textarea = document.createElement('textarea');
    textarea.className = 'reader-editor';
    textarea.id = 'reader-editor';
    textarea.value = raw;
    textarea.setAttribute('aria-label', 'Editor de markdown del nodo');
    textarea.spellcheck = false;

    toolbar.appendChild(
      makeButton('reader-save', 'Guardar', async () => {
        status.textContent = 'Guardando…';
        let ok = false;
        try {
          ok = await deps.saveMarkdown(textarea.value);
        } catch (e) {
          ok = false;
        }
        if (ok) {
          renderPreview();
        } else {
          status.textContent = 'Error al guardar';
        }
      }),
    );
    toolbar.appendChild(makeButton('reader-cancel', 'Cancelar', () => renderPreview()));
    toolbar.appendChild(status);

    reader.appendChild(toolbar);
    reader.appendChild(textarea);
    textarea.focus();
  };

  const show = () => {
    const current = root.getAttribute('data-layout') || 'collapsed';
    // Re-triggering show while already in reader (toolbar + right-rail icon
    // both route here) must not trap previousLayout at 'reader'.
    if (current !== 'reader') previousLayout = current;
    root.setAttribute('data-layout', 'reader');
    if (reader) {
      renderPreview();
      reader.setAttribute('tabindex', '-1');
      reader.scrollTop = 0;
      if (typeof (reader as HTMLElement).focus === 'function') {
        (reader as HTMLElement).focus();
      }
    }
  };

  const hide = () => {
    editing = false;
    root.setAttribute('data-layout', previousLayout === 'reader' ? 'collapsed' : previousLayout);
    if (lastTrigger && typeof lastTrigger.focus === 'function') {
      lastTrigger.focus();
    }
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && root.getAttribute('data-layout') === 'reader') {
      event.preventDefault();
      // First Escape leaves edit mode (preserving the reader), second closes it.
      if (editing) {
        renderPreview();
        return;
      }
      hide();
    }
  };

  const onShowClick = (event: Event) => {
    lastTrigger = (event.currentTarget as HTMLElement) || showBtn as HTMLElement;
    if (root.getAttribute('data-layout') === 'reader') {
      hide();
      return;
    }
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
