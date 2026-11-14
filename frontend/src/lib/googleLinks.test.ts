import { describe, expect, it } from "vitest";
import { parseGoogleLink } from "@/lib/googleLinks";

describe("parseGoogleLink", () => {
  it("knows Docs, Sheets, Slides, Forms and Drive files", () => {
    expect(parseGoogleLink("https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit")?.kind).toBe(
      "doc",
    );
    expect(
      parseGoogleLink("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMn/edit#gid=0")?.kind,
    ).toBe("sheet");
    expect(parseGoogleLink("https://docs.google.com/presentation/d/1AbCdEfGhIjKlMn/")?.kind).toBe(
      "slides",
    );
    expect(
      parseGoogleLink("https://docs.google.com/forms/d/e/1AbCdEfGhIjKlMn/viewform")?.kind,
    ).toBe("form");
    expect(parseGoogleLink("https://drive.google.com/file/d/1AbCdEfGhIjKlMn/view")?.kind).toBe(
      "file",
    );
    expect(parseGoogleLink("https://drive.google.com/open?id=1AbCdEfGhIjKlMn")?.id).toBe(
      "1AbCdEfGhIjKlMn",
    );
  });
  it("refuses look-alikes and other schemes", () => {
    expect(
      parseGoogleLink("https://docs.google.com.evil.example/document/d/1AbCdEfGhIjKlMn"),
    ).toBeNull();
    expect(parseGoogleLink("http://docs.google.com/document/d/1AbCdEfGhIjKlMn")).toBeNull();
    expect(parseGoogleLink("https://user@docs.google.com/document/d/1AbCdEfGhIjKlMn")).toBeNull();
    expect(parseGoogleLink("https://example.org/document/d/1AbCdEfGhIjKlMn")).toBeNull();
    expect(parseGoogleLink("see https://docs.google.com/document/d/1AbCdEfGhIjKlMn")).toBeNull();
  });
});
