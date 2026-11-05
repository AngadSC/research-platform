/** Stable colours for projects and people. Both shades pass AA with `text-on-vivid`. */
const VIVID = [
  { bg: "bg-vivid-1", text: "text-vivid-1" },
  { bg: "bg-vivid-2", text: "text-vivid-2" },
  { bg: "bg-vivid-3", text: "text-vivid-3" },
  { bg: "bg-vivid-4", text: "text-vivid-4" },
  { bg: "bg-vivid-5", text: "text-vivid-5" },
  { bg: "bg-vivid-6", text: "text-vivid-6" },
] as const;

/** The same id always gets the same colour. */
export function vivid(id: string) {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return VIVID[Math.abs(hash) % VIVID.length]!;
}

/** "Lee Lead" gives "LL"; an email gives its first letter. */
export function initials(name: string) {
  const words = name.split(/[\s@.]+/).filter((w) => /^\p{L}/u.test(w));
  const picked = name.includes("@") ? words.slice(0, 1) : [words[0], words[1]];
  return picked.map((w) => w?.[0]?.toUpperCase() ?? "").join("");
}
