// Fail if any installed npm package has a license outside the D2 allowlist.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OWN_PACKAGES = new Set(["research-workspace-frontend"]);
// Frontend bundles stay strict: no LGPL here.
const ALLOWED = new Set([
  "MIT",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "Apache-2.0",
  "ISC",
  "MPL-2.0",
  "PostgreSQL",
  "PSF-2.0",
  "Python-2.0",
  "0BSD",
  "CC0-1.0",
  "Unlicense",
  "BlueOak-1.0.0",
  "HPND",
]);
// CC-BY-4.0 is data-only; allowed for these packages alone.
const ALLOWED_FOR_PACKAGE = new Map([["caniuse-lite", new Set(["CC-BY-4.0"])]]);
// Unknown or missing license, verified from the package's metadata or LICENSE file.
// name -> [SPDX id, one-line reason]
const OVERRIDES = new Map();

const ALIASES = new Map([
  ["mit license", "MIT"],
  ["mit/x11", "MIT"],
  ["expat", "MIT"],
  ["bsd", "BSD-3-Clause"],
  ["bsd license", "BSD-3-Clause"],
  ["new bsd license", "BSD-3-Clause"],
  ["bsd 3-clause license", "BSD-3-Clause"],
  ["bsd 2-clause", "BSD-2-Clause"],
  ["bsd 2-clause license", "BSD-2-Clause"],
  ["simplified bsd license", "BSD-2-Clause"],
  ["apache 2.0", "Apache-2.0"],
  ["apache-2", "Apache-2.0"],
  ["apache license 2.0", "Apache-2.0"],
  ["apache license, version 2.0", "Apache-2.0"],
  ["apache license version 2.0", "Apache-2.0"],
  ["apache software license", "Apache-2.0"],
  ["isc license", "ISC"],
  ["isc license (iscl)", "ISC"],
  ["mpl 2.0", "MPL-2.0"],
  ["mozilla public license 2.0", "MPL-2.0"],
  ["psf", "PSF-2.0"],
  ["psf license", "PSF-2.0"],
  ["python software foundation license", "PSF-2.0"],
  ["postgresql license", "PostgreSQL"],
  ["cc0", "CC0-1.0"],
  ["cc0 1.0 universal", "CC0-1.0"],
  ["the unlicense", "Unlicense"],
  ["blue oak model license 1.0.0", "BlueOak-1.0.0"],
  ["historical permission notice and disclaimer", "HPND"],
  ["cc by 4.0", "CC-BY-4.0"],
]);
const CANONICAL = new Map([...ALLOWED, "CC-BY-4.0"].map((spdx) => [spdx.toLowerCase(), spdx]));
const TOKEN_RE = /\(|\)|\bAND\b|\bOR\b|\bWITH\b|[^()\s][^()]*?(?=\s+(?:AND|OR|WITH)\b|\s*\)|$)/g;

function normaliseLeaf(text) {
  const key = text.trim().replace(/\s+/g, " ").toLowerCase();
  return ALIASES.get(key) ?? CANONICAL.get(key) ?? text.trim();
}

// True if the SPDX-ish expression passes. OR needs one allowed part, AND needs all.
function evaluate(expr, pkgName) {
  const tokens = expr.match(TOKEN_RE) ?? [];
  let pos = 0;
  const peek = () => tokens[pos];
  const leafOk = (text) => {
    const spdx = normaliseLeaf(text);
    return ALLOWED.has(spdx) || (ALLOWED_FOR_PACKAGE.get(pkgName)?.has(spdx) ?? false);
  };
  const parseOr = () => {
    let result = parseAnd();
    while (peek() === "OR") {
      pos += 1;
      result = parseAnd() || result;
    }
    return result;
  };
  const parseAnd = () => {
    let result = parseAtom();
    while (peek() === "AND") {
      pos += 1;
      result = parseAtom() && result;
    }
    return result;
  };
  const parseAtom = () => {
    const tok = peek();
    pos += 1;
    if (tok === "(") {
      const result = parseOr();
      pos += 1; // closing ")"
      return result;
    }
    if (peek() === "WITH") pos += 2; // "X WITH exception" is judged by X alone
    return leafOk(tok ?? "");
  };
  return tokens.length > 0 && parseOr();
}

// The legacy "licenses" field lists alternatives, so they combine with OR.
function licenseOf(pkg) {
  const field = pkg.license ?? pkg.licenses;
  if (!field) return "";
  if (typeof field === "string") return field;
  const list = Array.isArray(field) ? field : [field];
  return list.map((item) => (typeof item === "string" ? item : (item.type ?? ""))).join(" OR ");
}

function addPackage(pkgDir, out) {
  const manifest = join(pkgDir, "package.json");
  if (existsSync(manifest)) {
    const pkg = JSON.parse(readFileSync(manifest, "utf8"));
    out.push({
      name: pkg.name ?? basename(pkgDir),
      version: pkg.version ?? "?",
      license: licenseOf(pkg),
    });
  }
  const nested = join(pkgDir, "node_modules");
  if (existsSync(nested)) collect(nested, out);
}

function collect(nodeModules, out) {
  for (const entry of readdirSync(nodeModules, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
    const dir = join(nodeModules, entry.name);
    if (entry.name.startsWith("@")) {
      for (const sub of readdirSync(dir, { withFileTypes: true })) {
        if (sub.isDirectory()) addPackage(join(dir, sub.name), out);
      }
    } else {
      addPackage(dir, out);
    }
  }
}

const packages = [];
collect(join(ROOT, "node_modules"), packages);

const offenders = new Set();
let checked = 0;
for (const pkg of packages) {
  if (OWN_PACKAGES.has(pkg.name)) continue;
  checked += 1;
  let license = pkg.license.trim();
  if (OVERRIDES.has(pkg.name)) {
    license = OVERRIDES.get(pkg.name)[0];
  } else if (license === "" || license.toUpperCase() === "UNKNOWN") {
    offenders.add(`${pkg.name} ${pkg.version}: missing license`);
    continue;
  }
  if (!evaluate(license, pkg.name)) offenders.add(`${pkg.name} ${pkg.version}: ${license}`);
}

if (offenders.size > 0) {
  console.log(`License check failed for ${offenders.size} package(s):`);
  for (const line of [...offenders].sort()) console.log(`  - ${line}`);
  process.exit(1);
}
console.log(`License check passed for ${checked} npm packages.`);
