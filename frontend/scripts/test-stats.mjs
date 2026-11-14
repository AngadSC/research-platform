// Runs scripts/stats_test.py against src/lib/stats/stats.py inside real Pyodide (the same runtime
// and packages the browser gets). Needs `npm run pyodide:fetch` first. Run: npm run test:stats
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loadPyodide, version } from "pyodide";

const root = new URL("../", import.meta.url);
const indexURL = fileURLToPath(new URL(`public/pyodide/v${version}/`, root));
const started = Date.now();
const py = await loadPyodide({ indexURL });
await py.loadPackage(["pandas", "scipy", "statsmodels", "openpyxl"], { messageCallback() {} });
const source = await readFile(new URL("src/lib/stats/stats.py", root), "utf8");
py.globals.set("SOURCE", source);
try {
  py.runPython(source);
  py.runPython(await readFile(new URL("scripts/stats_test.py", root), "utf8"));
} catch (e) {
  console.error(e.message); // a Python traceback; the default print dumps the whole runtime
  process.exit(1);
}
const failed = py.globals.get("RESULT");
console.log(`pyodide v${version}, ${((Date.now() - started) / 1000).toFixed(1)} s`);
process.exit(failed ? 1 : 0);
