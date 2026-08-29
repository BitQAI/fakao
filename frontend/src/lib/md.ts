const esc = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function inline(s: string): string {
  let out = esc(s);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return out;
}

const HEADING_RE = /^(#{1,3})\s+(.*)$/;
const HR_RE = /^(\*{3,}|-{3,})$/;
const QUOTE_RE = /^>\s?(.*)$/;
const LIST_RE = /^([-*+]|\d+\.)\s+(.*)$/;
const TABLE_SEP_RE = /^\s*\|?[\s:|-]+\|?\s*$/;

function tableRow(line: string, head: boolean): string {
  const cells = line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
  const tag = head ? "th" : "td";
  return `<tr>${cells.map((c) => `<${tag}>${inline(c)}</${tag}>`).join("")}</tr>`;
}

export function mdToHtml(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let listTag: "ul" | "ol" | null = null;
  let listBuf: string[] = [];
  let paraBuf: string[] = [];
  let table: string[] | null = null;

  const flushList = () => {
    if (listTag && listBuf.length) {
      out.push(`<${listTag}>${listBuf.join("")}</${listTag}>`);
    }
    listTag = null;
    listBuf = [];
  };
  const flushPara = () => {
    if (paraBuf.length) {
      out.push(`<p>${paraBuf.map((l, i) => `${i ? "<br/>" : ""}${inline(l)}`).join("")}</p>`);
      paraBuf = [];
    }
  };
  const flushTable = () => {
    if (table) {
      const [head, ...body] = table;
      out.push(
        `<table><thead>${tableRow(head, true)}</thead>` +
        `<tbody>${body.map((r) => tableRow(r, false)).join("")}</tbody></table>`,
      );
    }
    table = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const t = raw.trim();

    if (t === "") {
      flushList();
      flushPara();
      flushTable();
      continue;
    }

    const m = HEADING_RE.exec(t);
    if (m) {
      flushList(); flushPara(); flushTable();
      const level = m[1].length + 1;
      out.push(`<h${level}>${inline(m[2])}</h${level}>`);
      continue;
    }

    if (t.startsWith("|") && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1].trim())) {
      flushList(); flushPara(); flushTable();
      table = [t];
      i += 1; // 跳过分隔行
      continue;
    }
    if (table) {
      if (t.startsWith("|")) {
        table.push(t);
        continue;
      }
      flushTable();
    }

    if (HR_RE.test(t)) {
      flushList(); flushPara();
      out.push("<hr/>");
      continue;
    }

    const q = QUOTE_RE.exec(t);
    if (q) {
      flushList(); flushPara();
      out.push(`<blockquote>${inline(q[1])}</blockquote>`);
      continue;
    }

    const l = LIST_RE.exec(t);
    if (l) {
      flushPara();
      const tag: "ul" | "ol" = /^\d/.test(l[1]) ? "ol" : "ul";
      if (listTag !== tag) {
        flushList();
        listTag = tag;
      }
      listBuf.push(`<li>${inline(l[2])}</li>`);
      continue;
    }

    flushList();
    paraBuf.push(t);
  }

  flushList();
  flushPara();
  flushTable();
  return out.join("");
}
