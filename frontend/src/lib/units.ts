/** The same unit families as backend/labs/units.py, so the screen can offer compatible units and
 * preview what a use leaves. The server does the real conversion. */
const FAMILIES: Record<string, Record<string, number>> = {
  volume: { L: 1, dL: 0.1, cL: 0.01, mL: 0.001, uL: 1e-6, nL: 1e-9 },
  mass: { kg: 1000, g: 1, mg: 1e-3, ug: 1e-6, ng: 1e-9 },
  amount: { mol: 1, mmol: 1e-3, umol: 1e-6, nmol: 1e-9 },
};
const ALIASES: Record<string, string> = {
  liter: "l",
  liters: "l",
  litre: "l",
  litres: "l",
  milliliter: "ml",
  milliliters: "ml",
  millilitre: "ml",
  millilitres: "ml",
  microliter: "ul",
  microlitre: "ul",
  gram: "g",
  grams: "g",
  kilogram: "kg",
  milligram: "mg",
  microgram: "ug",
  mole: "mol",
};
const DISPLAY: Record<string, string> = { ul: "µL", ug: "µg", umol: "µmol" };

export const normalize = (unit: string) => {
  const t = unit.toLowerCase().replace(/[\s.]/g, "").replace(/[µμ]/g, "u");
  return ALIASES[t] ?? t;
};

const familyOf = (unit: string) => {
  const u = normalize(unit);
  return Object.values(FAMILIES).find((f) => Object.keys(f).some((k) => normalize(k) === u));
};
const factor = (f: Record<string, number>, unit: string) => {
  const u = normalize(unit);
  return f[Object.keys(f).find((k) => normalize(k) === u)!]!;
};

/** Units that convert to and from `unit`, as labelled for people. Empty for vials, tubes and so on. */
export function compatibleUnits(unit: string): string[] {
  const fam = familyOf(unit);
  if (!fam) return [];
  return Object.keys(fam).map((k) => DISPLAY[normalize(k)] ?? k);
}

/** `amount` of `from` in `to`, or null if they are not the same kind of unit. */
export function convert(amount: number, from: string, to: string): number | null {
  if (normalize(from) === normalize(to)) return amount;
  const fam = familyOf(from);
  if (!fam || fam !== familyOf(to)) return null;
  return (amount * factor(fam, from)) / factor(fam, to);
}

/** A stock number without trailing zeros: "99.99", not "99.990000". */
export const trimNumber = (value: string | number) => {
  const n = Number(value);
  return Number.isFinite(n) ? String(Number(n.toFixed(6))) : String(value);
};
