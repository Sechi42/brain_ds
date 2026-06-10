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
  // inline code BEFORE bold/italic so `**x**` inside code stays literal
  line = line.replace(/`([^`]+)`/g, "<code>$1</code>");
  line = line.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  line = line.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  // links: [text](url) — escaped source, so quotes are already entities
  line = line.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return line;
}

const isTableRow = (line: string): boolean => /^\s*\|.*\|\s*$/.test(line);
const isTableSeparator = (line: string): boolean => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(line);

function splitCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

export function renderMarkdown(src: string): string {
  const escaped = escapeHtml(src || "");
  const lines = escaped.split(/\r?\n/);
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] || "";

    // fenced code blocks ```
    if (/^```/.test(line.trim())) {
      const lang = line.trim().slice(3).trim();
      const buffer: string[] = [];
      i += 1;
      while (i < lines.length && !/^```/.test((lines[i] || "").trim())) {
        buffer.push(lines[i] || "");
        i += 1;
      }
      i += 1; // skip closing fence
      const langAttr = lang ? ` data-lang="${lang}"` : "";
      html.push(`<pre class="md-code"${langAttr}><code>${buffer.join("\n")}</code></pre>`);
      continue;
    }

    // tables: header row + separator row (+ body rows)
    if (isTableRow(line) && isTableSeparator(lines[i + 1] || "")) {
      const headers = splitCells(line).map((c) => `<th>${renderInline(c)}</th>`);
      i += 2;
      const rows: string[] = [];
      while (i < lines.length && isTableRow(lines[i] || "")) {
        const cells = splitCells(lines[i] || "").map((c) => `<td>${renderInline(c)}</td>`);
        rows.push(`<tr>${cells.join("")}</tr>`);
        i += 1;
      }
      html.push(`<table class="md-table"><thead><tr>${headers.join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`);
      continue;
    }

    // unordered lists
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

    // ordered lists
    const olMatch = line.match(/^\d+[.)]\s+(.+)$/);
    if (olMatch) {
      const items: string[] = [];
      while (i < lines.length) {
        const m = (lines[i] || "").match(/^\d+[.)]\s+(.+)$/);
        if (!m) break;
        items.push(`<li>${renderInline(m[1])}</li>`);
        i += 1;
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    // blockquotes
    const quoteMatch = line.match(/^&gt;\s?(.*)$/);
    if (quoteMatch) {
      const quoted: string[] = [];
      while (i < lines.length) {
        const m = (lines[i] || "").match(/^&gt;\s?(.*)$/);
        if (!m) break;
        quoted.push(renderInline(m[1]));
        i += 1;
      }
      html.push(`<blockquote>${quoted.join("<br/>")}</blockquote>`);
      continue;
    }

    // horizontal rule
    if (/^(-{3,}|\*{3,})\s*$/.test(line.trim())) {
      html.push("<hr/>");
      i += 1;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
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
