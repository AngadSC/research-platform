// Puts the Pyodide runtime and the Python packages the statistics engine needs into
// public/pyodide/v<version>/, so the app serves them from its own origin (no CDN at runtime).
// Run: npm run pyodide:fetch   (the production Dockerfile runs it before the build)
//
// Core files come from node_modules/pyodide. Package wheels are downloaded from the Pyodide
// release on jsDelivr and checked against the sha256 in pyodide-lock.json; a mismatch fails.
// openpyxl is not in the Pyodide release, so it comes from PyPI with a pinned sha256 and is
// added to the served lockfile, which lets the worker load it by name like the others.
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const pkgDir = new URL("node_modules/pyodide/", root);
const { version } = JSON.parse(await readFile(new URL("package.json", pkgDir), "utf8"));
const out = new URL(`public/pyodide/v${version}/`, root);
const CDN = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;

const CORE = ["pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"];
const WANT = ["numpy", "pandas", "scipy", "statsmodels", "openpyxl"];
const PYPI = [
  {
    name: "openpyxl",
    version: "3.1.5",
    file_name: "openpyxl-3.1.5-py2.py3-none-any.whl",
    url: "https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl",
    sha256: "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2",
    imports: ["openpyxl"],
    depends: ["et-xmlfile"],
  },
  {
    name: "et-xmlfile",
    version: "2.0.0",
    file_name: "et_xmlfile-2.0.0-py3-none-any.whl",
    url: "https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl",
    sha256: "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa",
    imports: ["et_xmlfile"],
    depends: [],
  },
];

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const readOrNull = (url) => readFile(url).catch(() => null);

await mkdir(out, { recursive: true });
for (const f of CORE) await copyFile(new URL(f, pkgDir), new URL(f, out));

const lock = JSON.parse(await readFile(new URL("pyodide-lock.json", pkgDir), "utf8"));
for (const p of PYPI) {
  const { url: _url, ...entry } = p;
  lock.packages[p.name] = {
    ...entry,
    install_dir: "site",
    package_type: "package",
    unvendored_tests: false,
  };
}
await writeFile(new URL("pyodide-lock.json", out), JSON.stringify(lock));

// Dependency closure of what we need, per the lockfile.
const needed = new Set();
const queue = [...WANT];
while (queue.length) {
  const name = queue.shift();
  if (needed.has(name)) continue;
  if (!lock.packages[name]) throw new Error(`${name} is not in pyodide-lock.json`);
  needed.add(name);
  queue.push(...lock.packages[name].depends);
}

let total = 0;
for (const name of [...needed].sort()) {
  const p = lock.packages[name];
  const dest = new URL(p.file_name, out);
  let buf = await readOrNull(dest);
  if (!buf || sha256(buf) !== p.sha256) {
    const url = PYPI.find((x) => x.name === name)?.url ?? CDN + p.file_name;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
    buf = Buffer.from(await res.arrayBuffer());
    const got = sha256(buf);
    if (got !== p.sha256)
      throw new Error(`${p.file_name}: sha256 ${got}, lockfile says ${p.sha256}`);
    await writeFile(dest, buf);
    console.log(`downloaded ${p.file_name} (${buf.length} bytes)`);
  }
  total += buf.length;
}
console.log(`pyodide v${version}: ${needed.size} packages (${total} bytes) in ${out.pathname}`);
