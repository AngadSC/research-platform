// "Open in Overleaf" (D388): a browser form POST to Overleaf's public /docs address, in a new tab.
// Only this one address is ever posted to; the site's form-action rule (deploy/Caddyfile) allows it.
export const OVERLEAF_DOCS = "https://www.overleaf.com/docs";

/** A .tex file, or a .zip that may hold LaTeX (the server checks inside the zip). */
export const overleafFile = (a: {
  original_filename: string;
  drive_file_id?: string | null;
  external_url?: string | null;
  office_copy?: boolean;
}) =>
  !a.drive_file_id &&
  !a.external_url &&
  !a.office_copy &&
  /\.(tex|zip)$/i.test(a.original_filename);

/** Opens a tab first (while the click still counts, so the browser does not block it), then posts
 * the fields into it. Call this synchronously from the click, before any await. */
export function openOverleafWindow() {
  const name = `overleaf-${Date.now()}`;
  const win = window.open("about:blank", name);
  if (win) win.opener = null;
  return {
    post(fields: [string, string][]) {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = OVERLEAF_DOCS;
      form.target = win ? name : "_blank";
      form.style.display = "none";
      for (const [k, v] of fields) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = k;
        input.value = v;
        form.appendChild(input);
      }
      document.body.appendChild(form);
      form.submit();
      form.remove();
    },
    close: () => win?.close(),
  };
}

const BS = String.fromCharCode(92); // a backslash

/** Makes text safe to put inside LaTeX. */
export function escapeTex(s: string) {
  return s
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[\\{}^~#$%&_]/g, (c) =>
      "\\{}^~".includes(c) ? `${BS}char${c.charCodeAt(0)}{}` : `${BS}${c}`,
    );
}

/** A small starting document: the manuscript's title and the project's people. Nothing else. */
export function manuscriptTemplate(title: string, authors: string[]) {
  const who = authors.map(escapeTex).filter(Boolean).join(` ${BS}and `);
  return [
    String.raw`\documentclass{article}`,
    String.raw`\usepackage[utf8]{inputenc}`,
    `${BS}title{${escapeTex(title)}}`,
    `${BS}author{${who}}`,
    String.raw`\date{\today}`,
    "",
    String.raw`\begin{document}`,
    String.raw`\maketitle`,
    "",
    String.raw`\begin{abstract}`,
    "Write your abstract here.",
    String.raw`\end{abstract}`,
    "",
    String.raw`\section{Introduction}`,
    "",
    String.raw`\end{document}`,
    "",
  ].join("\n");
}
