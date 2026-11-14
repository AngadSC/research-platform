/** A greeting for the top of the page that follows the time and the day, so it is not the same
 * words every visit. The choice among equals is fixed for a day, so it does not flicker. */
const first = (name: string) => name.trim().split(/\s+/)[0] ?? "";

export function greeting(now: Date, name: string): string {
  const who = first(name);
  const hour = now.getHours();
  const day = now.getDay(); // 0 Sunday
  const pick = <T>(options: T[]) =>
    options[(now.getFullYear() * 400 + now.getMonth() * 31 + now.getDate()) % options.length]!;
  const withName = (text: string) => (who ? `${text}, ${who}` : text);

  if (hour < 5) return withName(pick(["Burning the midnight oil", "Still up", "Late night"]));
  if (hour < 12) {
    if (day === 1) return withName(pick(["Happy Monday", "Good morning", "Fresh week"]));
    if (day === 5) return withName(pick(["Happy Friday", "Good morning", "Last push of the week"]));
    if (day === 0 || day === 6)
      return withName(pick(["Good morning", "Easy does it", "Weekend mode"]));
    return withName(pick(["Good morning", "Good morning", "Welcome back", "Rise and shine"]));
  }
  if (hour < 17) {
    if (day === 5) return withName(pick(["Good afternoon", "Nearly the weekend", "Back at it"]));
    return withName(pick(["Good afternoon", "Back at it", "Welcome back"]));
  }
  return withName(pick(["Good evening", "Evening", "Welcome back", "Still at it"]));
}
