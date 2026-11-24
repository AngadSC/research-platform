import { useState } from "react";
import { Slides, slidesOf, type Slide } from "@/components/documents/Slides";
import { Spreadsheet } from "@/components/documents/Spreadsheet";
import { sheetsOf, type Sheet } from "@/lib/sheet";

/** A spreadsheet document: keeps its sheets in state and hands the saved shape up. */
export function SheetEditor({
  initial,
  editable,
  onChange,
}: {
  initial: unknown[];
  editable: boolean;
  onChange: (content: unknown[]) => void;
}) {
  const [sheets, setSheets] = useState<Sheet[]>(() => sheetsOf(initial));
  return (
    <Spreadsheet
      tall
      label="Spreadsheet"
      editable={editable}
      sheets={sheets}
      onChange={(next) => {
        setSheets(next);
        onChange([{ type: "sheet", sheets: next }]);
      }}
    />
  );
}

/** A presentation document. */
export function SlidesEditor({
  initial,
  editable,
  onChange,
}: {
  initial: unknown[];
  editable: boolean;
  onChange: (content: unknown[]) => void;
}) {
  const [slides, setSlides] = useState<Slide[]>(() => slidesOf(initial));
  return (
    <Slides
      label="Presentation"
      editable={editable}
      slides={slides}
      onChange={(next) => {
        setSlides(next);
        onChange(next);
      }}
    />
  );
}
