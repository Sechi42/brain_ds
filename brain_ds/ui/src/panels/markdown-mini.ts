// @ts-nocheck

export function escapeHtml(value: string): string {
  const raw = String(value ?? "");
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(value: string): string {
  let line = value;
  // wikilinks: [[NodeLabel]]
  line = line.replace(/\[\[([^\]]+)\]\]/g, '<a class="wikilink" data-node-label="$1">$1</a>');
  line = line.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return line;
}

export function renderMarkdown(src: string): string {
  const escaped = escapeHtml(src || "");
  const lines = escaped.split(/\r?\n/);
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] || "";
    const listMatch = line.match(/^[-*]\s+(.+)$/);
    if (listMatch) {
      const items: string[] = [];
      while (i < lines.length) {
        const m = (lines[i] || "").match(/^[-*]\s+(.+)$/);
        if (!m) break;
        items.push(`<li>${renderInline(m[1])}</li>`);
        i += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (line.trim()) {
      html.push(`<p>${renderInline(line)}</p>`);
    }
    i += 1;
  }
  return html.join("\n");
}
