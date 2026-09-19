/** Split OKF frontmatter from the Markdown body. */
export function splitFrontmatter(content: string): { frontmatter: string | null; body: string } {
  const match = /^---\n([\s\S]*?)\n---\n?/.exec(content);
  if (!match) return { frontmatter: null, body: content };
  return { frontmatter: match[1] ?? "", body: content.slice(match[0].length) };
}

export type Citation = { label: string; title: string; url?: string | undefined };

const FOOTNOTE = /^\[\^([^\]]+)\]:\s*(.+)$/gm;
const LINK = /^\[(.+)\]\((.+)\)$/;

/** The footnote definitions a BRD cites its sources with (S1, C2, ...). */
export function citations(content: string): Citation[] {
  const found: Citation[] = [];
  for (const match of content.matchAll(FOOTNOTE)) {
    const label = match[1] ?? "";
    const text = (match[2] ?? "").trim();
    const link = LINK.exec(text);
    found.push(link ? { label, title: link[1] ?? text, url: link[2] } : { label, title: text });
  }
  return found;
}
