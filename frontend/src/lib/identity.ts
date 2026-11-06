/** "Lee Lead" gives "LL"; an email gives its first letter. */
export function initials(name: string) {
  const words = name.split(/[\s@.]+/).filter((w) => /^\p{L}/u.test(w));
  const picked = name.includes("@") ? words.slice(0, 1) : [words[0], words[1]];
  return picked.map((w) => w?.[0]?.toUpperCase() ?? "").join("");
}
