import { describe, expect, it } from "vitest";
import { codesIn, scanFile } from "@/lib/participantScan";

const columns = [
  { id: "n", name: "English narrative" },
  { id: "t", name: "Transcript" },
  { id: "tr", name: "Translation" },
  { id: "c", name: "Consent form" },
];

const names = (r: ReturnType<typeof scanFile>) => r.matches.map((m) => m.name);

describe("scanFile", () => {
  it("matches an entry named in the file name", () => {
    const r = scanFile({ fileName: "P-001_transcript.pdf", columns, participantCode: "P-001" });
    expect(names(r)).toEqual(["Transcript"]);
    expect(r.matches[0]).toMatchObject({ confidence: "sure", found: "in the file name" });
    expect(r.basis).toBe("name");
    expect(r.hasOwnCode).toBe(true);
  });

  it("reads the words in the file and treats close words as the same", () => {
    const r = scanFile({
      fileName: "scan.pdf",
      text: "Verbatim transcription of the session. Translated into English by the team.",
      columns,
      participantCode: "P-001",
    });
    expect(names(r)).toEqual(expect.arrayContaining(["Transcript", "Translation"]));
    expect(names(r)).not.toContain("Consent form");
    expect(r.basis).toBe("text");
  });

  it("needs every word of a two-word entry to call it sure", () => {
    const sure = scanFile({
      fileName: "notes.txt",
      text: "English narrative retell, session one",
      columns,
      participantCode: "P-001",
    });
    expect(sure.matches.find((m) => m.componentId === "n")?.confidence).toBe("sure");
    const half = scanFile({
      fileName: "narrative.txt",
      text: "",
      columns,
      participantCode: "P-001",
    });
    expect(half.matches.find((m) => m.componentId === "n")?.confidence).toBe("maybe");
  });

  it("warns when the file names a different participant", () => {
    const r = scanFile({
      fileName: "P-002 consent.pdf",
      columns,
      participantCode: "P-001",
    });
    expect(r.otherCodes).toEqual(["P-2"]);
    expect(r.hasOwnCode).toBe(false);
  });

  it("suggests nothing when nothing matches", () => {
    expect(
      scanFile({ fileName: "IMG_0042.jpg", columns, participantCode: "P-001" }).matches,
    ).toEqual([]);
  });
});

describe("codesIn", () => {
  it("treats P012 and P-12 as the same code", () => {
    expect([...codesIn("P012 and P-12 and p_12")]).toEqual(["P-12"]);
  });
});
