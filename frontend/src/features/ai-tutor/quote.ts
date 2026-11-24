/** Quoting part of an answer into a question: a markdown blockquote above the question. */

export const QUOTE_MAX_CHARS = 1000;

export function buildQuoted(quote: string, question: string): string {
  const clipped =
    quote.length > QUOTE_MAX_CHARS ? `${quote.slice(0, QUOTE_MAX_CHARS - 1)}…` : quote;
  const block = clipped
    .split(/\r?\n/)
    .map((line) => `> ${line}`.trimEnd())
    .join("\n");
  return `${block}\n\n${question}`;
}

/** Splits a sent message into its leading quote (if any) and the question. */
export function splitQuote(content: string): { quote: string | null; body: string } {
  if (!content.startsWith("> ")) return { quote: null, body: content };
  const lines = content.split("\n");
  const quoted: string[] = [];
  let i = 0;
  while (i < lines.length && lines[i].startsWith(">")) {
    quoted.push(lines[i].replace(/^>\s?/, ""));
    i += 1;
  }
  while (i < lines.length && lines[i].trim() === "") i += 1;
  return { quote: quoted.join("\n"), body: lines.slice(i).join("\n") };
}
