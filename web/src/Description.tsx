import { memo, type ReactNode } from "react";

/**
 * Job descriptions are stored as plain text. This rebuilds their structure for
 * reading: section headings, bullet and numbered lists, and paragraphs. Nothing
 * is dropped or reworded; only the layout changes.
 */

const BULLET = /^\s*(?:[•●▪■◦‣·*–—-]|o(?=\s{2,}))\s+/;
const NUMBERED = /^\s*(?:\(?\d{1,2}[.)]|[a-z][.)])\s+/;
const SECTION_WORDS =
  /^(about|overview|summary|introduction|the (role|team|opportunity|job|position)|role|position|job (description|summary|purpose|title|requirements?)|description|responsibilit|key |core |primary |essential|duties|what (you|we|you'?ll|your)|who (you|we)|you (will|are|have|bring)|your (role|impact|team|profile|responsibilit|background|skills|day)|we (are|offer)|meet |requirements?|qualifications?|minimum|basic|preferred|required|desired|must[- ]have|nice[- ]to[- ]have|good[- ]to[- ]have|bonus|skills?|technical|education|experience|eligibility|benefits?|perks|compensation|salary|pay |why |how |our |life at|location|work(ing)? |equal opportunity|additional|other |note|disclaimer|selection process|stipend|duration|number of openings|who can apply|certifications?)/i;

type Block =
  | { kind: "heading"; text: string }
  | { kind: "para"; text: string }
  | { kind: "list"; ordered: boolean; items: string[]; start?: number };

function isHeading(line: string, next: string | undefined): boolean {
  if (line.startsWith("## ")) return true;
  const text = line.trim();
  if (text.length < 3 || text.length > 72 || !next) return false;
  if (BULLET.test(line) || NUMBERED.test(line)) return false;
  if (/[.!?;,]$/.test(text)) return false;                 // a sentence, not a title
  const words = text.replace(/:$/, "").split(/\s+/);
  if (words.length > 9) return false;
  const endsWithColon = text.endsWith(":");
  const allCaps = text === text.toUpperCase() && /[A-Z]/.test(text);
  const titleCase = words.filter((w) => /^[A-Z0-9(&]/.test(w)).length >= Math.ceil(words.length * 0.6);
  return endsWithColon || allCaps || (SECTION_WORDS.test(text) && (titleCase || words.length <= 4));
}

export function parseDescription(source: string): Block[] {
  const lines = source.replace(/\r/g, "").split("\n").map((l) => l.replace(/\s+$/, ""));
  const blocks: Block[] = [];
  const nextFilled = (from: number) => lines.slice(from).find((l) => l.trim());
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const bullet = BULLET.test(line), numbered = !bullet && NUMBERED.test(line);
    if (bullet || numbered) {
      const text = line.replace(bullet ? BULLET : NUMBERED, "").trim();
      const last = blocks[blocks.length - 1];
      if (!text) continue;
      if (last?.kind === "list" && last.ordered === numbered) last.items.push(text);
      else {
        // Keep the source's own number: a numbered list is often interrupted by
        // sub-bullets, and each piece must not restart at 1.
        const start = numbered ? Number(/\d+/.exec(line)?.[0]) || undefined : undefined;
        blocks.push({ kind: "list", ordered: numbered, items: [text], start });
      }
    } else if (isHeading(line, nextFilled(i + 1))) {
      blocks.push({ kind: "heading", text: line.replace(/^## /, "").trim().replace(/:$/, "") });
    } else {
      blocks.push({ kind: "para", text: line.trim() });
    }
  }
  return blocks;
}

/** "Label: value" lines read better with the label set apart. */
function withLabel(text: string): ReactNode {
  const m = /^([A-Z][A-Za-z /&-]{2,28}):\s+(\S.*)$/.exec(text);
  return m ? <><span className="font-medium text-ink">{m[1]}:</span> {m[2]}</> : text;
}

export default memo(function Description({ text }: { text: string }) {
  const blocks = parseDescription(text);
  return (
    <div className="max-w-[78ch] text-[15px] leading-[1.7] [contain:content]">
      {blocks.map((b, i) =>
        b.kind === "heading" ? (
          <h3 key={i} className="mb-1.5 mt-6 text-[15.5px] font-semibold text-ink first:mt-0">{b.text}</h3>
        ) : b.kind === "list" ? (
          b.ordered ? (
            <ol key={i} start={b.start} className="my-2 list-decimal space-y-1.5 pl-6 font-medium marker:text-faint">
              {b.items.map((item, j) => <li key={j} className="pl-1">{withLabel(item)}</li>)}
            </ol>
          ) : (
            <ul key={i} className="my-2 list-disc space-y-1.5 pl-6 marker:text-faint">
              {b.items.map((item, j) => <li key={j} className="pl-1">{withLabel(item)}</li>)}
            </ul>
          )
        ) : (
          <p key={i} className="mt-3 text-[color-mix(in_srgb,var(--ink)_88%,var(--paper))] first:mt-0">{withLabel(b.text)}</p>
        ),
      )}
    </div>
  );
});
