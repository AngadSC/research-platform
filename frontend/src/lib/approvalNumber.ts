export interface FoundApproval {
  /** As written, for example "Pro00151738". */
  number: string;
  /** The board's short name when one came before the number, for example "REB". Else "". */
  board: string;
}

const BOARDS = "REB|HREB|CREB|IRB|REC|ERB|IACUC|HSREB";
// "REB Pro00151738", "IRB #2023-0456", "HREB No. 20-123": a board name, then something number-like
// that contains a digit.
const WITH_BOARD = new RegExp(
  `\\b(${BOARDS})\\b[\\s#:.\\-]*(?:no\\.?\\s*)?([A-Za-z]{0,4}\\d[\\w./-]{3,}\\w)`,
  "gi",
);
// A bare Pro number (University of Alberta style) with no board in front.
const BARE_PRO = /\bPro\d{6,}\b/g;

/** Approval numbers a person has already written in free text (a project's description). A
 * hint only: the person confirms it before anything is saved. */
export function findApprovalNumbers(text: string): FoundApproval[] {
  const found = new Map<string, FoundApproval>();
  for (const m of text.matchAll(WITH_BOARD)) {
    const number = m[2]!;
    found.set(number.toLowerCase(), { number, board: m[1]!.toUpperCase() });
  }
  for (const m of text.matchAll(BARE_PRO)) {
    if (!found.has(m[0].toLowerCase())) found.set(m[0].toLowerCase(), { number: m[0], board: "" });
  }
  return [...found.values()];
}
