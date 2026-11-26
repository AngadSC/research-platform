import type { SampleKind, SampleStatus } from "@/lib/api-types";

export const KINDS: { value: SampleKind; label: string }[] = [
  { value: "plasmid", label: "Plasmid" },
  { value: "strain", label: "Strain" },
  { value: "primer", label: "Primer" },
  { value: "construct", label: "Construct" },
  { value: "cell_line", label: "Cell line" },
  { value: "antibody", label: "Antibody" },
  { value: "protein", label: "Protein or enzyme batch" },
  { value: "other", label: "Other" },
];
export const STATUSES: { value: SampleStatus; label: string }[] = [
  { value: "in_use", label: "In use" },
  { value: "verified", label: "Verified" },
  { value: "archived", label: "Archived" },
];
export const labelOf = (list: { value: string; label: string }[], v: string) =>
  list.find((x) => x.value === v)?.label ?? v;

export type FieldKey =
  | "backbone"
  | "insert"
  | "resistance"
  | "tag"
  | "species"
  | "genotype"
  | "sequence"
  | "concentration"
  | "buffer"
  | "made_on";
export interface KindField {
  key: FieldKey;
  label: string;
  type?: "text" | "date" | "long";
}
const PLASMID: KindField[] = [
  { key: "backbone", label: "Backbone" },
  { key: "insert", label: "Insert" },
  { key: "resistance", label: "Resistance" },
  { key: "tag", label: "Tag" },
];
/** The fields each kind has, besides code, name, description, owner and status. */
export const KIND_FIELDS: Record<SampleKind, KindField[]> = {
  plasmid: PLASMID,
  construct: PLASMID,
  strain: [
    { key: "species", label: "Species" },
    { key: "genotype", label: "Genotype" },
    { key: "resistance", label: "Resistance" },
  ],
  cell_line: [
    { key: "species", label: "Species" },
    { key: "genotype", label: "Genotype" },
  ],
  primer: [{ key: "sequence", label: "Sequence (5' to 3')", type: "long" }],
  antibody: [
    { key: "species", label: "Host" },
    { key: "concentration", label: "Concentration" },
  ],
  protein: [
    { key: "concentration", label: "Concentration" },
    { key: "buffer", label: "Buffer" },
    { key: "made_on", label: "Made on", type: "date" },
  ],
  other: [],
};

export const rowLetter = (row: number) => String.fromCharCode(64 + row);
export const who = (u: { display_name?: string; email: string }) => u.display_name || u.email;
