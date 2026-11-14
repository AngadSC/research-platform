import { describe, expect, it } from "vitest";
import { matchProject, parseCapture } from "@/lib/quickCapture";
import { greeting } from "@/lib/greeting";

const projects = [
  { id: "p1", name: "Paper 2" },
  { id: "p2", name: "Paper 3" },
  { id: "p3", name: "Thesis chapter" },
];
// Wednesday 2026-11-11, midday
const now = new Date(2026, 10, 11, 12, 0);

describe("parseCapture", () => {
  it("reads a title, a weekday and a project from one line", () => {
    const c = parseCapture("email Dr. Bhalloo Friday #paper2", projects, now);
    expect(c.title).toBe("email Dr. Bhalloo");
    expect(c.due).toBe("2026-11-13");
    expect(c.project?.id).toBe("p1");
  });
  it("understands the usual ways to say a day", () => {
    const due = (t: string) => parseCapture(t, projects, now).due;
    expect(due("a today")).toBe("2026-11-11");
    expect(due("a tomorrow")).toBe("2026-11-12");
    expect(due("a wednesday")).toBe("2026-11-18"); // the next one, not today
    expect(due("a this wednesday")).toBe("2026-11-11");
    expect(due("a next week")).toBe("2026-11-16");
    expect(due("a in 3 days")).toBe("2026-11-14");
    expect(due("a in 2 weeks")).toBe("2026-11-25");
    expect(due("a Dec 5")).toBe("2026-12-05");
    expect(due("a 5th Dec")).toBe("2026-12-05");
    expect(due("a 2027-01-09")).toBe("2027-01-09");
    expect(due("a Nov 1")).toBe("2027-11-01"); // already past this year
  });
  it("drops the little word before the date", () => {
    expect(parseCapture("send slides by fri", projects, now).title).toBe("send slides");
    expect(parseCapture("send slides due tomorrow", projects, now).title).toBe("send slides");
  });
  it("keeps a plain title with no date or project", () => {
    const c = parseCapture("  read the methods section ", projects, now);
    expect(c).toMatchObject({ title: "read the methods section", due: null, project: null });
  });
  it("does not read a word inside another as a date", () => {
    expect(parseCapture("summon the monitor", projects, now).due).toBeNull();
    expect(parseCapture("rate the satisfaction", projects, now).due).toBeNull();
  });
  it("puts the tag anywhere", () => {
    const c = parseCapture("#thesis write intro tomorrow", projects, now);
    expect(c.project?.id).toBe("p3");
    expect(c.title).toBe("write intro");
  });
});

describe("matchProject", () => {
  it("is not fooled by case or punctuation, and will not guess between two", () => {
    expect(matchProject("PAPER-2", projects)?.id).toBe("p1");
    expect(matchProject("paper", projects)).toBeNull();
    expect(matchProject("chap", projects)?.id).toBe("p3");
    expect(matchProject("", projects)).toBeNull();
  });
});

describe("greeting", () => {
  const at = (h: number, d = 11) => new Date(2026, 10, d, h);
  it("follows the time of day and uses the first name", () => {
    expect(greeting(at(9, 12), "Sam Lee")).toMatch(/, Sam$/);
    expect(greeting(at(3), "Sam")).toMatch(/^(Burning|Still|Late)/);
    expect(greeting(at(20), "Sam")).toMatch(/Sam$/);
  });
  it("is the same all day and says something for each day", () => {
    expect(greeting(at(9), "Sam")).toBe(greeting(at(10), "Sam"));
    expect(["Happy Monday, Sam", "Good morning, Sam", "Fresh week, Sam"]).toContain(
      greeting(new Date(2026, 10, 9, 9), "Sam"),
    );
  });
  it("works without a name", () => {
    expect(greeting(at(9), "")).not.toMatch(/,/);
  });
});
