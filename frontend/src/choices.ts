// Extract discrete, clickable answer options from an assistant message that poses
// a choice — so the user can click instead of typing. Deliberately CONSERVATIVE:
// it only fires when the message actually asks a question AND lists short, distinct
// options, so ordinary prose (or a list that isn't a question) never turns into
// buttons. Yes/no approval prompts are handled by the separate approval UI, so the
// caller should skip those.

const strip = (s: string): string =>
  s
    .replace(/^[-*•\d.()a-zA-Z\s]*?[.)]\s*/, "") // any leftover list marker
    .replace(/^[*_`"']+|[*_`"']+$/g, "") // wrapping markdown/quotes
    .replace(/\s*[—:.;,]+\s*$/g, "") // trailing punctuation
    .replace(/\s+/g, " ")
    .trim();

const finalize = (arr: string[]): string[] => {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of arr) {
    const s = strip(raw);
    const key = s.toLowerCase();
    if (s && s.length <= 80 && !seen.has(key)) {
      seen.add(key);
      out.push(s);
    }
  }
  return out.slice(0, 6); // never flood the UI
};

export function parseChoices(text: string): string[] {
  if (!text || !text.includes("?")) return []; // must be a question

  // 1) Enumerated / bulleted options: "1. Foo", "- Bar", "a) Baz". Most reliable.
  const listed: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*(?:\d{1,2}[.)]|[-*•]|\(?[a-zA-Z][).])\s+(.+\S)\s*$/);
    if (m) {
      // For "**Label** — long description", keep just the label if there is one.
      const label = m[1].match(/^\*\*(.+?)\*\*/);
      listed.push(label ? label[1] : m[1]);
    }
  }
  const fromList = finalize(listed);
  if (fromList.length >= 2) return fromList;

  // 2) Inline "A, B, or C?" — only in the last question sentence, and only if the
  //    options are short and word-like (so we don't shred a prose sentence on "or").
  const q = (text.match(/[^?\n]*\?/g) || []).pop()?.trim() || "";
  let seg = q;
  const after = q.match(
    /(?:choose|which|would you (?:like|prefer)|do you (?:want|prefer)|prefer|pick|select|option[s]?|:)\s*(.+)\?$/i,
  );
  if (after) seg = after[1];
  if (/\bor\b/i.test(seg)) {
    const parts = seg
      .replace(/\band\/or\b|\bor\b/gi, ",")
      .split(",")
      .map((s) => s.replace(/[.?!]+$/g, "").trim())
      .filter(Boolean);
    // With an explicit trigger ("choose:", "which…") the options can be a few words;
    // WITHOUT one (bare "X or Y?") a long part means we're slicing prose, not options,
    // so require terse (≤3-word) options and bail otherwise — better nothing than junk.
    const maxWords = after ? 6 : 3;
    if (parts.length >= 2 && parts.every((p) => p.length <= 40 && p.split(/\s+/).length <= maxWords)) {
      return finalize(parts);
    }
  }

  return [];
}
