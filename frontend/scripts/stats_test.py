"""Checks stats.py against published results. Run by scripts/test-stats.mjs inside Pyodide, after
stats.py has been run in the same namespace. Reference values are typed in from the textbook and R
dataset results named next to each check (the R outputs are the documented ones for those
datasets); the data are the classic public datasets.

Every test goes through engine_load / engine_run (the worker's path), and every saved script is
executed against the same file to prove it runs on its own and prints the same summary.
"""

import contextlib
import io
import json
import os

FAILS = []
CHECKS = [0]
os.makedirs("/tmp/stats", exist_ok=True)
os.chdir("/tmp/stats")


def close(got, want, what, tol=1e-3):
    CHECKS[0] += 1
    if got is None or abs(got - want) > tol * max(1.0, abs(want)):
        FAILS.append(f"{what}: got {got}, expected {want}")


def ok(cond, what):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(what)


def write(name, text):
    with open(name, "w", encoding="utf-8") as f:
        f.write(text)


def csv_of(columns):
    keys = list(columns)
    rows = zip(*(columns[k] for k in keys))
    return ",".join(keys) + "\n" + "\n".join(",".join("" if v is None else str(v) for v in r) for r in rows) + "\n"


def load(name, sheet=None, options=None):
    out, _ = engine_load(name, name, sheet, json.dumps(options) if options is not None else None)  # noqa: F821
    return json.loads(out)


def run(name, test, sheet=None, options=None, **params):
    """Load and run, check the xlsx and the saved script, and return the result."""
    shape_ = load(name, sheet, options)
    assert "error" not in shape_, shape_
    out, xlsx = engine_run(test, json.dumps(params))  # noqa: F821
    result = json.loads(out)
    if "error" in result:
        FAILS.append(f"{test} on {name}: unexpected error {result['error']}")
        return result
    ok(xlsx[:2] == b"PK", f"{test}: xlsx is a zip")
    for chart in result["charts"]:
        values = chart.get("points") or [v for g in chart.get("groups", []) for v in g["values"]] or chart.get("bars", [])
        ok(len(values) <= 5000, f"{test}: chart {chart['title']} has {len(values)} values")
    ok(result["code"].isascii(), f"{test}: saved script is not pure ASCII")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # as bytes, the way python reads the saved file, so a coding comment would take effect
        exec(compile(result["code"].encode("utf-8"), "saved_script.py", "exec"), {"__name__": "__main__"})
    ok(result["summary"] in buf.getvalue(), f"{test}: saved script printed a different summary:\n{buf.getvalue()[:400]}")
    return result


def same_numbers(result):
    """Run the saved script's own read_data and test call on the same file: every number must match."""
    code = result["code"]
    ns = {"__name__": "saved_script"}
    exec(compile(code.encode("utf-8"), "saved_script.py", "exec"), ns)
    read, call = code.rsplit("    df = ", 1)[1].split("\n", 2)[:2]
    ns["df"] = eval(read, ns)
    again = _clean(eval(call.strip()[len("print_result("):-1], ns))  # noqa: F821
    for key in ("summary", "tables", "warnings", "n"):
        ok(again[key] == result[key], f"{result['test']}: the saved script gives a different {key}:\n{again[key]}\n{result[key]}")


def issue(shape_, id_):
    return next((i for i in shape_.get("issues", []) if i["id"] == id_), None)


def error(name, test, contains, **params):
    load(name)
    out, xlsx = engine_run(test, json.dumps(params))  # noqa: F821
    msg = json.loads(out).get("error", "")
    ok(contains in msg and xlsx is None, f"{test}: expected an error with {contains!r}, got {msg!r}")


def table(result, title):
    for t in result.get("tables", []):
        if t["title"].startswith(title):
            return t
    FAILS.append(f"{result.get('test')}: no table {title!r}")
    return {"columns": [], "rows": [[]]}


def cell(result, title, column, row=0):
    t = table(result, title)
    try:
        return t["rows"][row][t["columns"].index(column)]
    except (ValueError, IndexError):
        FAILS.append(f"{result.get('test')}: no {column!r} in {title!r} row {row}")
        return None


# Student's sleep data (R `sleep`): extra hours of sleep for 10 patients on two drugs.
G1 = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0.0, 2.0]
G2 = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4]
write("sleep.csv", csv_of({"id": list(range(1, 21)), "drug": [1] * 10 + [2] * 10, "extra": G1 + G2}))
write("sleep_wide.csv", csv_of({"drug1": G1, "drug2": G2}))

# R t.test(extra ~ group, data = sleep): Welch t = -1.8608, df = 17.776, p = 0.07939, CI -3.3654832 0.2054832
r = run("sleep.csv", "t_independent", outcome="extra", group="drug")
close(cell(r, "Welch", "t"), -1.8608, "Welch t")
close(cell(r, "Welch", "df"), 17.776, "Welch df")
close(cell(r, "Welch", "p"), 0.07939, "Welch p")
close(cell(r, "Welch", "95% CI low"), -3.3654832, "Welch CI low")
close(cell(r, "Welch", "95% CI high"), 0.2054832, "Welch CI high")
# Cohen's d with the pooled SD: -1.58 / sqrt((1.789010^2 + 2.002249^2) / 2) = -0.8322
close(cell(r, "Welch", "Cohen's d"), -0.8322, "Cohen's d")
ok("did not differ significantly" in r["summary"] and "t(17.8) = 1.86, p = .079" in r["summary"], r["summary"])
# var.equal = TRUE: t = -1.8608, df = 18, p = 0.07919
r = run("sleep.csv", "t_independent", outcome="extra", group="drug", variant="student")
close(cell(r, "Student", "p"), 0.07919, "Student p")
close(cell(r, "Student", "df"), 18, "Student df")

# R t.test(extra ~ group, data = sleep, paired = TRUE): t = -4.0621, df = 9, p = 0.002833 (group 1 minus 2)
r = run("sleep_wide.csv", "t_paired", before="drug1", after="drug2")
close(cell(r, "Paired", "t"), 4.0621, "paired t")
close(cell(r, "Paired", "p"), 0.002833, "paired p")
close(cell(r, "Paired", "Mean difference"), 1.58, "paired mean difference")
ok(r["summary"].startswith("Values rose"), r["summary"])

# R t.test(sleep$extra[1:10]): t = 1.3257, df = 9, p = 0.2176, CI -0.5297804 2.0297804
r = run("sleep_wide.csv", "t_one_sample", column="drug1", mu=0)
close(cell(r, "One-sample", "t"), 1.3257, "one-sample t")
close(cell(r, "One-sample", "p"), 0.2176, "one-sample p")
close(cell(r, "One-sample", "95% CI low"), -0.5297804, "one-sample CI")

# Mann-Whitney (Conover; R wilcox.test(x, y)): W = 17, p = 0.1111
write("mw.csv", csv_of({"sex": ["m"] * 5 + ["f"] * 4, "score": [19, 22, 16, 29, 24, 20, 11, 17, 12]}))
r = run("mw.csv", "mann_whitney", outcome="score", group="sex")
close(cell(r, "Mann-Whitney", "U"), 3, "U for f (17 for m)")
close(cell(r, "Mann-Whitney", "p"), 0.1111, "Mann-Whitney p")
close(cell(r, "Mann-Whitney", "Rank-biserial r"), -0.7, "rank-biserial r")

# Wilcoxon signed-rank (Hollander & Wolfe, depression scale; R V = 40, one-sided p = 0.01953)
X = [1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30]
Y = [0.878, 0.647, 0.598, 2.05, 1.06, 1.29, 1.06, 3.14, 1.29]
write("hw.csv", csv_of({"second": Y, "first": X}))
r = run("hw.csv", "wilcoxon", before="second", after="first")
close(cell(r, "Wilcoxon", "Sum of positive ranks"), 40, "V")
close(cell(r, "Wilcoxon", "p"), 0.0390625, "two-sided p")
close(cell(r, "Wilcoxon", "Rank-biserial r"), 35 / 45, "matched-pairs r")

# PlantGrowth (Dobson 1983; R aov): F(2, 27) = 4.846, p = 0.01591; SS 3.76634 and 10.49209
CTRL = [4.17, 5.58, 5.18, 6.11, 4.50, 4.61, 5.17, 4.53, 5.33, 5.14]
TRT1 = [4.81, 4.17, 4.41, 3.59, 5.87, 3.83, 6.03, 4.89, 4.32, 4.69]
TRT2 = [6.31, 5.12, 5.54, 5.50, 5.37, 5.29, 4.92, 6.15, 5.80, 5.26]
write("plants.csv", csv_of({"weight": CTRL + TRT1 + TRT2, "group": ["ctrl"] * 10 + ["trt1"] * 10 + ["trt2"] * 10}))
r = run("plants.csv", "anova_oneway", outcome="weight", group="group")
close(cell(r, "One-way ANOVA", "F"), 4.846, "ANOVA F")
close(cell(r, "One-way ANOVA", "p"), 0.01591, "ANOVA p")
close(cell(r, "One-way ANOVA", "Sum of squares"), 3.76634, "SS between")
close(cell(r, "Effect size", "Value", 0), 3.76634 / 14.25843, "eta squared")
close(cell(r, "Effect size", "Value", 1), (3.76634 - 2 * 10.49209 / 27) / (14.25843 + 10.49209 / 27), "omega squared")
# R TukeyHSD: trt1-ctrl -0.371 p 0.3908711; trt2-ctrl 0.494 p 0.1979960; trt2-trt1 0.865 [0.1737839, 1.5562161] p 0.0120064
close(cell(r, "Tukey", "Mean difference", 0), -0.371, "Tukey trt1-ctrl")
close(cell(r, "Tukey", "p", 0), 0.3908711, "Tukey p trt1-ctrl")
close(cell(r, "Tukey", "p", 1), 0.1979960, "Tukey p trt2-ctrl")
close(cell(r, "Tukey", "Mean difference", 2), 0.865, "Tukey trt2-trt1")
close(cell(r, "Tukey", "95% CI low", 2), 0.1737839, "Tukey CI low")
close(cell(r, "Tukey", "p", 2), 0.0120064, "Tukey p trt2-trt1")
ok('"trt2" and "trt1" (p = .012)' in r["summary"], r["summary"])

# describe by group (R aggregate on PlantGrowth): means 5.032, 4.661, 5.526; SDs 0.5830914, 0.7936757, 0.4425733
r = run("plants.csv", "describe", columns=["weight"], group="group")
for i, (m, sd) in enumerate([(5.032, 0.5830914), (4.661, 0.7936757), (5.526, 0.4425733)]):
    close(cell(r, "Summary", "Mean", i), m, f"mean {i}")
    close(cell(r, "Summary", "SD", i), sd, f"sd {i}")

# Linear regression with a categorical predictor (R lm(weight ~ group)): R² = 0.2641, F = 4.846
r = run("plants.csv", "linear_regression", outcome="weight", predictors=["group"])
close(cell(r, "Model fit", "R²"), 0.2641, "R² PlantGrowth", tol=1e-2)
close(cell(r, "Model fit", "F"), 4.846, "F PlantGrowth")
close(cell(r, "Coefficients", "B", 0), 5.032, "intercept = ctrl mean")
close(cell(r, "Coefficients", "B", 1), -0.371, "group: trt1")
ok(cell(r, "Coefficients", "Term", 2) == "group: trt2", "dummy name")

# Kruskal-Wallis (Hollander & Wolfe, mucociliary efficiency; R kruskal.test): chi-squared = 0.77143, df = 2, p = 0.68
write("kw.csv", csv_of({
    "rate": [2.9, 3.0, 2.5, 2.6, 3.2, 3.8, 2.7, 4.0, 2.4, 2.8, 3.4, 3.7, 2.2, 2.0],
    "who": ["normal"] * 5 + ["obstructive"] * 4 + ["asbestosis"] * 5,
}))
r = run("kw.csv", "kruskal", outcome="rate", group="who")
close(cell(r, "Kruskal", "H"), 0.77143, "H")
close(cell(r, "Kruskal", "p"), 0.68, "Kruskal p", tol=5e-3)

# ToothGrowth (R aov(len ~ supp * factor(dose))): supp F = 15.572, dose F = 92.000, interaction F = 4.107 on 2, 54
LEN = {
    ("VC", 0.5): [4.2, 11.5, 7.3, 5.8, 6.4, 10, 11.2, 11.2, 5.2, 7],
    ("VC", 1): [16.5, 16.5, 15.2, 17.3, 22.5, 17.3, 13.6, 14.5, 18.8, 15.5],
    ("VC", 2): [23.6, 18.5, 33.9, 25.5, 26.4, 32.5, 26.7, 21.5, 23.3, 29.5],
    ("OJ", 0.5): [15.2, 21.5, 17.6, 9.7, 14.5, 10, 8.2, 9.4, 16.5, 9.7],
    ("OJ", 1): [19.7, 23.3, 23.6, 26.4, 20, 25.2, 25.8, 21.2, 14.5, 27.3],
    ("OJ", 2): [25.5, 26.4, 22.4, 24.5, 24.8, 30.9, 26.4, 27.3, 29.4, 23],
}
write("teeth.csv", csv_of({
    "len": [v for vs in LEN.values() for v in vs],
    "supp": [k[0] for k, vs in LEN.items() for _ in vs],
    "dose": [k[1] for k, vs in LEN.items() for _ in vs],
}))
r = run("teeth.csv", "anova_twoway", outcome="len", factor_a="supp", factor_b="dose")
close(cell(r, "Two-way", "F", 0), 15.572, "supp F")
close(cell(r, "Two-way", "F", 1), 92.000, "dose F")
close(cell(r, "Two-way", "F", 2), 4.107, "interaction F")
close(cell(r, "Two-way", "p", 2), 0.02186, "interaction p")
close(cell(r, "Two-way", "Partial η²", 0), 205.35 / (205.35 + 712.11), "partial eta² supp")
# shapiro.test(ToothGrowth$len): W = 0.96743, p = 0.1091
r = run("teeth.csv", "normality", column="len")
close(cell(r, "Normality", "Shapiro-Wilk W"), 0.96743, "W")
close(cell(r, "Normality", "p"), 0.1091, "Shapiro p")
ok("looks normally distributed" in r["summary"], r["summary"])

# Chi-square (Agresti 2007, party by gender; R chisq.test): X-squared = 30.07, df = 2, p = 2.954e-07
COUNTS = {("F", "Dem"): 762, ("F", "Ind"): 327, ("F", "Rep"): 468, ("M", "Dem"): 484, ("M", "Ind"): 239, ("M", "Rep"): 477}
write("party.csv", csv_of({
    "gender": [k[0] for k, n in COUNTS.items() for _ in range(n)],
    "party": [k[1] for k, n in COUNTS.items() for _ in range(n)],
}))
r = run("party.csv", "chi_square", rows="gender", cols="party")
close(cell(r, "Tests", "Value"), 30.07, "chi-square", tol=1e-3)
close(cell(r, "Tests", "p"), 2.954e-07, "chi-square p")
close(cell(r, "Effect size", "Value"), (30.0701 / 2757) ** 0.5, "Cramér's V")
ok("χ²(2, N = 2757) = 30.07, p < .001" in r["summary"], r["summary"])
# Fisher's tea tasting (Agresti; R fisher.test): p = 0.4857
TEA = {("milk", "milk"): 3, ("milk", "tea"): 1, ("tea", "milk"): 1, ("tea", "tea"): 3}
write("tea.csv", csv_of({"poured": [k[0] for k, n in TEA.items() for _ in range(n)], "guess": [k[1] for k, n in TEA.items() for _ in range(n)]}))
r = run("tea.csv", "chi_square", rows="poured", cols="guess")
close(cell(r, "Tests", "p", 1), 0.4857, "Fisher p")
ok(any("expect fewer than 5" in w for w in r["warnings"]) is False and "Fisher" in r["summary"], r["summary"])

# Correlation (Hollander & Wolfe p. 187; R cor.test): r = 0.5711816, CI -0.1497426 0.8955795, p = 0.1082;
# Kendall tau = 0.4444444, p = 0.1194; Spearman rho = 0.6
CX = [44.4, 45.9, 41.9, 53.3, 44.7, 44.1, 50.7, 45.2, 60.1]
CY = [2.6, 3.1, 2.5, 5.0, 3.6, 4.0, 5.2, 2.8, 3.8]
write("cor.csv", csv_of({"x": CX, "y": CY}))
r = run("cor.csv", "correlation", columns=["x", "y"])
close(cell(r, "Pairs", "r"), 0.5711816, "Pearson r")
close(cell(r, "Pairs", "95% CI low"), -0.1497426, "Pearson CI low")
close(cell(r, "Pairs", "95% CI high"), 0.8955795, "Pearson CI high")
close(cell(r, "Pairs", "p"), 0.1082, "Pearson p")
ok(r["charts"][0]["kind"] == "scatter" and "line" in r["charts"][0], "scatter with line")
r = run("cor.csv", "correlation", columns=["x", "y"], method="kendall")
close(cell(r, "Pairs", "τ"), 0.4444444, "Kendall tau")
close(cell(r, "Pairs", "p"), 0.1194, "Kendall p")
r = run("cor.csv", "correlation", columns=["x", "y"], method="spearman")
close(cell(r, "Pairs", "rs"), 0.6, "Spearman rho")

# Linear regression, R `cars` (lm(dist ~ speed)): -17.5791 + 3.9324 speed, R² 0.6511, adj 0.6438, F(1, 48) = 89.57
SPEED = [4, 4, 7, 7, 8, 9, 10, 10, 10, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15,
         15, 16, 16, 17, 17, 17, 18, 18, 18, 18, 19, 19, 19, 20, 20, 20, 20, 20, 22, 23, 24, 24, 24, 24, 25]
DIST = [2, 10, 4, 22, 16, 10, 18, 26, 34, 17, 28, 14, 20, 24, 28, 26, 34, 34, 46, 26, 36, 60, 80, 20, 26,
        54, 32, 40, 32, 40, 50, 42, 56, 76, 84, 36, 46, 68, 32, 48, 52, 56, 64, 66, 54, 70, 92, 93, 120, 85]
write("cars.csv", csv_of({"speed": SPEED, "dist": DIST}))
r = run("cars.csv", "linear_regression", outcome="dist", predictors=["speed"])
close(cell(r, "Coefficients", "B", 0), -17.5791, "cars intercept")
close(cell(r, "Coefficients", "B", 1), 3.9324, "cars slope")
close(cell(r, "Coefficients", "SE", 1), 0.4155, "cars slope SE")
close(cell(r, "Model fit", "R²"), 0.6511, "cars R²")
close(cell(r, "Model fit", "Adjusted R²"), 0.6438, "cars adj R²")
close(cell(r, "Model fit", "F"), 89.57, "cars F")
ok(r["charts"][0]["kind"] == "scatter" and abs(r["charts"][0]["line"]["slope"] - 3.9324) < 1e-3, "regression line")

# Logistic regression with one 0/1 predictor equals the 2x2 table: B = ln(OR), SE = sqrt(sum of 1/n) (Woolf)
cells = {(1, "yes"): 30, (1, "no"): 10, (0, "yes"): 15, (0, "no"): 25}
write("logit.csv", csv_of({"x": [k[0] for k, n in cells.items() for _ in range(n)], "y": [k[1] for k, n in cells.items() for _ in range(n)]}))
r = run("logit.csv", "logistic_regression", outcome="y", predictors=["x"])
close(cell(r, "Coefficients", "B", 1), 1.6094379, "log odds ratio")
close(cell(r, "Coefficients", "SE", 1), 0.24**0.5, "SE of log odds ratio")
close(cell(r, "Coefficients", "Odds ratio", 1), 5.0, "odds ratio")
close(cell(r, "Coefficients", "B", 0), -0.5108256, "intercept = log odds at x = 0")
ok('"y" is "yes"' in r["summary"], r["summary"])
# and with a text predictor, which is dummy-coded
write("logit2.csv", csv_of({"arm": ["drug" if k[0] else "placebo" for k, n in cells.items() for _ in range(n)], "y": [k[1] for k, n in cells.items() for _ in range(n)]}))
r = run("logit2.csv", "logistic_regression", outcome="y", predictors=["arm"])
close(cell(r, "Coefficients", "Odds ratio", 1), 0.2, "odds ratio placebo vs drug")

# Frequencies
write("freq.csv", csv_of({
    "colour": ["red"] * 5 + ["blue"] * 3 + [None] * 2,
    "size": ["S", "M", "L", "S", "M", "L", "S", "M", "L", "S"],
    "email": [f"person{i}@example.test" for i in range(10)],
}))
r = run("freq.csv", "frequencies", columns=["colour"])
ok(table(r, "Counts")["rows"][:2] == [["blue", 3, 30.0, 37.5], ["red", 5, 50.0, 62.5]], table(r, "Counts")["rows"])
r = run("freq.csv", "frequencies", columns=["email"])
ok(not any("example.test" in str(v) for row in table(r, "Counts")["rows"] for v in row), "IDs not listed")
r = run("freq.csv", "frequencies", columns=["colour", "size"])
ok(table(r, "Counts")["rows"][-1][-1] == 8, "cross-table total")
# Many distinct values: only repeated ones, at most 50
write("many.csv", csv_of({"code": [f"c{i % 70}" if i < 140 else f"u{i}" for i in range(400)]}))
r = run("many.csv", "frequencies", columns=["code"])
t = table(r, "Counts")
ok(len(t["rows"]) == 51 and "50 most common" in t["note"] and not any(str(row[0]).startswith("u") for row in t["rows"]), t["note"])

# Charts are capped at 5,000 values
write("big.csv", csv_of({"v": [i % 97 for i in range(12000)], "g": ["a", "b"] * 6000}))
r = run("big.csv", "describe", columns=["v"], group="g")
ok(sum(len(g["values"]) for g in r["charts"][0]["groups"]) == 5000, "histogram capped")
r = run("big.csv", "t_independent", outcome="v", group="g")
ok(r["n"] == 12000, "n for big file")

# Reading: semicolons, BOM, latin-1, TSV, missing values and text in a number column
with open("euro.csv", "wb") as f:
    f.write("﻿nom;âge;groupe\nAndré;31;a\nZoë;n/a;b\nÉmile;45;a\nLéa;29;b\n".encode("utf-8"))
s = load("euro.csv")
ok([c["name"] for c in s["columns"]] == ["nom", "âge", "groupe"], s)
ok([c["kind"] for c in s["columns"]] == ["text", "numeric", "categorical"], [c["kind"] for c in s["columns"]])
ok(s["columns"][1]["missing"] == 1, s["columns"][1])
with open("latin.csv", "wb") as f:
    f.write("name,score\nJosé,1\nMüller,2\n".encode("latin-1"))
s = load("latin.csv")
ok(s.get("columns", [{}])[0].get("sample") == ["José", "Müller"], s)
write("tabs.tsv", "a\tb\n1\t2\n3\t4\n")
ok([c["name"] for c in load("tabs.tsv")["columns"]] == ["a", "b"], "tsv")
write("messy.csv", csv_of({"score": [1, 2, "three", 4, 5, "n/a", 7, 8, 9, 10], "g": ["a", "b"] * 5}))
s = load("messy.csv")
ok(s["columns"][0]["kind"] == "numeric", s["columns"][0])
r = run("messy.csv", "describe", columns=["score"])
ok(any("1 of the values" in w for w in r["warnings"]), r["warnings"])
close(cell(r, "Summary", "N"), 8, "non-numbers become missing")

# XLSX with two sheets, including text that looks like a formula
import openpyxl

wb = openpyxl.Workbook()
wb.active.title = "Notes"
wb.active.append(["note"])
wb.active.append(["fake data for tests"])
ws = wb.create_sheet("Data")
ws.append(["score", "group"])
for v, g in zip(G1 + G2, ["=1+1"] * 10 + ["b"] * 10):
    ws.append([v, g])
    ws.cell(ws.max_row, 2).data_type = "s"
wb.save("book.xlsx")
s = load("book.xlsx")
ok(s["sheets"] == ["Notes", "Data"] and s["sheet"] == "Notes", s)
s = load("book.xlsx", "Data")
ok(s["sheet"] == "Data" and s["rows"] == 20, s)
r = run("book.xlsx", "t_independent", sheet="Data", outcome="score", group="group")
close(cell(r, "Welch", "t"), -1.8608, "t from xlsx")
ok("sheet='Data'" in r["code"] and "openpyxl" in r["code"], "script reads the sheet")
_, xlsx = engine_run("t_independent", json.dumps({"outcome": "score", "group": "group"}))  # noqa: F821
out = openpyxl.load_workbook(io.BytesIO(xlsx))
ok(out.sheetnames[0] == "Summary" and len(out.sheetnames) == 4, out.sheetnames)
ok(out["Descriptives"]["A3"].value == "=1+1" and out["Descriptives"]["A3"].data_type == "s", "formula text stays text")
ok(load("book.xlsx", "Nope").get("error") == 'The workbook has no sheet called "Nope".', "bad sheet")

# A file or column name can't inject code into the saved script. Before ascii(), a "coding:gbk" comment
# in the first lines switched the source encoding, and a GBK lead byte ate the backslash repr() puts
# before the quote, closing the string. LEAD is a CJK letter whose last UTF-8 byte is such a lead byte.
LEAD = next(
    chr(cp) for cp in range(0x4E00, 0x9FFF)
    if len(chr(cp).encode()[:2].decode("gbk", "replace")) == 1 and len((chr(cp).encode()[2:] + b"\\").decode("gbk", "replace")) == 1
)
EVIL = "coding:gbk " + LEAD + "'+str(print(\"INJ\" + \"ECTED\"))#\""
for name, col in [(EVIL + ".csv", "score"), ("evilcol.csv", EVIL)]:
    write(name, csv_of({col: G1 + G2}))
    r = run(name, "describe", columns=[col])
    ok(r.get("code", "").startswith("# -*- coding: utf-8 -*-\n"), f"saved script for {col!r} starts with the utf-8 line")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(r["code"].encode("utf-8"), "saved_script.py", "exec"), {"__name__": "__main__"})
    ok("INJECTED" not in buf.getvalue(), f"saved script ran code from a name: {buf.getvalue()[:300]}")

# A backslash in a column name is not allowed in a sheet name (run() fails if the workbook can't be made)
write("slash.csv", csv_of({"a\\b": ["x", "y", "x"]}))
run("slash.csv", "frequencies", columns=["a\\b"])

# Bad inputs: plain-English errors
write("three.csv", csv_of({"v": [1, 2, 3, 4, 5, 6], "g": ["a", "a", "b", "b", "c", "c"], "empty": [None] * 6, "word": ["x"] * 6}))
error("three.csv", "t_independent", "needs exactly two groups", outcome="v", group="g")
error("three.csv", "mann_whitney", "Use Kruskal-Wallis", outcome="v", group="g")
error("three.csv", "describe", "has no numbers", columns=["empty"])
error("three.csv", "t_one_sample", "has no numbers", column="word")
error("three.csv", "correlation", "at least two columns", columns=["v"])
error("three.csv", "anova_oneway", "at least two groups", outcome="v", group="word")
error("three.csv", "t_paired", "two different columns", before="v", after="v")
error("three.csv", "describe", 'no column called "nope"', columns=["nope"])
error("three.csv", "t_independent", "Fill in every choice", outcome="v")
error("three.csv", "logistic_regression", "exactly two values", outcome="g", predictors=["v"])
error("three.csv", "linear_regression", "both the outcome and a predictor", outcome="v", predictors=["v"])
error("plants.csv", "describe", "Pick a column with 20 groups or fewer", columns=["weight"], group="weight")
error("three.csv", "nonsense", "not available")
ok(json.loads(engine_load("missing.csv", "missing.csv")[0]).get("error", "").startswith("Something went wrong"), "missing file")  # noqa: F821
write("empty.csv", "")
ok(load("empty.csv").get("error") == "The file is empty.", "empty file")
write("notes.docx", "hello")
ok("CSV, TSV, TXT or XLSX" in load("notes.docx").get("error", ""), "unknown type")
write("header.csv", "a,b\n")
ok(load("header.csv").get("error") == "The file has no rows of data.", "header only")

# Messy files: problems found on load, explained, with LoadOptions that fix them -----------------

# Clean files show no issues
for name in ("sleep.csv", "plants.csv", "cars.csv", "teeth.csv", "party.csv", "euro.csv"):
    ok(load(name)["issues"] == [], f"{name} is clean but has issues: {load(name)['issues']}")
ok(load("book.xlsx", "Data")["issues"] == [], load("book.xlsx", "Data")["issues"])

# Missing-value codes far from the other values, and text in a number column (from the UX "awkward" file)
A = ["N/A", 11, 10, 999, 7, 18, "-", 4, 18, 8, 13, "NA", 3, 10, 16, 8, 15, "-", 4, 9, 1, 1, 11, 10]
write("codes.csv", csv_of({"a": A, "g": ["x", "y"] * 12, "b": [0.42, "<0.01", 0.25, 0.76, 0.3, 0.5, 0.6, 0.7] * 3}))
s = load("codes.csv")
i = issue(s, "missing:a:999")
ok(i and i["action"] == "Treat 999 as missing" and "far from its other values (1 to 18)" in i["message"], s["issues"])
ok(issue(s, "text:a") and '2 values are not ("-")' in issue(s, "text:a")["message"], s["issues"])
ok(issue(s, "text:b") and '3 values are not ("<0.01")' in issue(s, "text:b")["message"], s["issues"])
r = run("codes.csv", "describe", columns=["a"])
close(cell(r, "Summary", "Mean"), (177 + 999) / 20, "mean with 999 in it")
r = run("codes.csv", "describe", options=i["fix"], columns=["a"])
close(cell(r, "Summary", "Mean"), 177 / 19, "mean with 999 as missing")
ok("missing={'a': [999]}" in r["code"], "script treats 999 as missing")
same_numbers(r)
s = load("codes.csv", options=i["fix"])
ok(issue(s, "missing:a:999")["applied"] and issue(s, "missing:a:999")["fix"] == {"header": 0, "skip": 0}, s["issues"])
# Real values near 999, and 99 inside a plausible age range, are left alone; -9 in a 1-7 scale and -99 in 0-100 are not
write("near.csv", csv_of({
    "rt": [850, 999, 1012, 930, 1100, 1200, 905, 977],
    "top": [900, 950, 960, 990, 998, 999, 930, 940],
    "age": [18, 25, 33, 41, 52, 65, 99, 70],
    "likert": [1, 3, 7, 5, -9, 2, 4, 6],
    "pct": [0, 50, 100, 75, -99, 20, 30, 40],
}))
s = load("near.csv")
ok({i["id"] for i in s["issues"]} == {"missing:likert:-9", "missing:pct:-99"}, s["issues"])

# Decimal commas with ";" (from the UX "european" file), including 1.234,5 grouping
EU = zip(["3,7", "3,5", "2,5", "2,9", "4,5", "6", "6,2", "6,6"], ["9.771,50", "1.406,50", "512,25", "7.700,50"] * 2)
write("eu.csv", "id;arm;wert;gehalt\n" + "".join(f"{k};{'AB'[k % 2]};{v};{g}\n" for k, (v, g) in enumerate(EU)))
s = load("eu.csv")
i = issue(s, "decimal")
ok(i and i["action"] == "Read 3,5 as 3.5" and i["fix"] == {"header": 0, "skip": 0, "decimal": ",", "thousands": "."}, s["issues"])
ok("numeric" not in [c["kind"] for c in s["columns"]][2:], s["columns"])
r = run("eu.csv", "t_independent", options=i["fix"], outcome="gehalt", group="arm")
close(cell(r, "Descriptives", "Mean", 0), (9771.5 + 512.25) / 2, "1.234,5 grouping")
same_numbers(r)
s = load("eu.csv", options=i["fix"])
ok([c["kind"] for c in s["columns"]][2:] == ["numeric", "numeric"] and issue(s, "decimal")["applied"], s)
# Not offered when a column already uses a decimal point, or in a comma-separated file
write("mixed.csv", "a;b\n1,5;0.25\n2,5;0.5\n3;0.75\n")
ok(issue(load("mixed.csv"), "decimal") and "fix" not in issue(load("mixed.csv"), "decimal"), load("mixed.csv")["issues"])
write("quoted.csv", 'a,b\n"1,5",x\n"2,5",y\n"3,5",x\n')
ok(issue(load("quoted.csv"), "decimal") and "fix" not in issue(load("quoted.csv"), "decimal"), load("quoted.csv")["issues"])

# Qualtrics: the question-text and ImportId rows are left out automatically, with an undo
Q = ['StartDate,Q1,Score,Group', 'Start Date,"How much do you agree?\nPick one",Total score,Condition',
     '"{""ImportId"":""startDate""}","{""ImportId"":""QID1""}","{""ImportId"":""QID3""}","{""ImportId"":""QID4""}"']
Q += [f"2026-01-{d:02d} 10:00:00,{'Agree' if d % 3 else 'Disagree'},{10 + d},{'Control' if d % 2 else 'Treatment'}" for d in range(1, 21)]
write("qualtrics.csv", "\n".join(Q) + "\n")
s = load("qualtrics.csv")
i = issue(s, "skip")
ok(s["rows"] == 20 and i["applied"] and "Qualtrics" in i["message"] and i["fix"] == {"header": 0, "skip": 0}, s)
ok(issue(s, "dates") and '"StartDate" looks like dates' in issue(s, "dates")["message"], s["issues"])
ok([c["kind"] for c in s["columns"]][2] == "numeric", s["columns"])
r = run("qualtrics.csv", "chi_square", rows="Q1", cols="Group")
ok(cell(r, "Counts", "Total", 2) == 20 and "skip=2" in r["code"], table(r, "Counts"))
same_numbers(r)
s = load("qualtrics.csv", options=i["fix"])
ok(s["rows"] == 22 and issue(s, "skip")["action"] == "Leave out those 2 rows" and not issue(s, "skip").get("applied"), s["issues"])

# REDCap and other repeated measures: warned on load and in between-groups results
write("redcap.csv", csv_of({
    "record_id": [f"P{p:03d}" for p in range(1, 9) for _ in range(3)],
    "redcap_event_name": ["baseline_arm_1", "week4_arm_1", "week8_arm_1"] * 8,
    "arm": [a for a in "ABABABAB" for _ in range(3)],
    "score": [12, 15, 19, 8, 9, 14, 22, 21, 25, 10, 13, 12, 17, 18, 24, 9, 11, 10, 20, 23, 26, 7, 12, 11],
}))
s = load("redcap.csv")
ok(issue(s, "repeats") and '"record_id" repeats (24 rows, 8 different values)' in issue(s, "repeats")["message"], s["issues"])
for test, params in (("t_independent", {"outcome": "score", "group": "arm"}),
                     ("kruskal", {"outcome": "score", "group": "redcap_event_name"}),
                     ("chi_square", {"rows": "arm", "cols": "redcap_event_name"})):
    r = run("redcap.csv", test, **params)
    ok(any("each row is a different person" in w for w in r["warnings"]), f"{test}: {r['warnings']}")
write("events.csv", csv_of({"redcap_event_name": ["a", "b"] * 5, "v": list(range(10)), "g": ["x"] * 5 + ["y"] * 5}))
ok('"redcap_event_name"' in (issue(load("events.csv"), "repeats") or {}).get("message", ""), load("events.csv")["issues"])
r = run("sleep.csv", "t_independent", outcome="extra", group="drug")
ok(not any("different person" in w for w in r["warnings"]), r["warnings"])

# UTF-16, with a byte order mark and without (from the UX "utf16" file)
TEXT = "id\tname\tscore\n" + "".join(f"{k}\t{n}\t{k % 7}\n" for k, n in enumerate(["José", "Muñoz", "Müller", "Zoë"] * 4))
for name, data in (("u16.txt", TEXT.encode("utf-16")), ("u16le.txt", TEXT.encode("utf-16-le")), ("u16be.txt", TEXT.encode("utf-16-be"))):
    with open(name, "wb") as f:
        f.write(data)
    s = load(name)
    ok(s.get("rows") == 16 and s["columns"][1]["sample"][:2] == ["José", "Muñoz"] and s["issues"] == [], f"{name}: {s}")
r = run("u16.txt", "describe", columns=["score"])
same_numbers(r)

# A title above the headers: offered in a workbook and a padded CSV, applied when the CSV can't be read otherwise
wb = openpyxl.Workbook()
wb.active.append(["My lab study - raw export (fake)"])
wb.active.append([])
wb.active.append(["Participant", "pre", "post"])
for k, (a, b) in enumerate(zip(G1, G2)):
    wb.active.append([f"P{k:03d}", a, b])
wb.save("title.xlsx")
s = load("title.xlsx")
i = issue(s, "header")
ok(i and i["action"] == "Use row 3 as the headers" and i["fix"] == {"header": 2} and len(s["issues"]) == 1, s["issues"])
r = run("title.xlsx", "t_paired", options=i["fix"], before="pre", after="post")
close(cell(r, "Paired", "t"), 4.0621, "paired t after the header fix")
ok("header=2" in r["code"], "script uses the header row")
same_numbers(r)
ok(issue(load("title.xlsx", options=i["fix"]), "header")["fix"] == {"header": 0}, "undo the header")
write("title_padded.csv", "Fake export,,\n\nid,pre,post\n" + "".join(f"{k},{a},{b}\n" for k, (a, b) in enumerate(zip(G1, G2))))
ok(issue(load("title_padded.csv"), "header")["fix"] == {"header": 2}, load("title_padded.csv")["issues"])
write("title.csv", "Fake export\nmade 2026-01-01\nid,pre,post\n" + "".join(f"{k},{a},{b}\n" for k, (a, b) in enumerate(zip(G1, G2))))
s = load("title.csv")
ok(s.get("rows") == 10 and issue(s, "header")["applied"] and "fix" not in issue(s, "header"), s)
r = run("title.csv", "t_paired", before="pre", after="post")
ok("header=2" in r["code"], "script uses the header row")
same_numbers(r)

# Units after every number (from the UX "awkward" file); a mix of units is left alone
write("units.csv", csv_of({"rt": [f"{v} ms" for v in (180, 201, 116, 112, 163)], "w": ["5 kg", "6kg", "7 lb", "5 kg", "8 kg"]}))
s = load("units.csv")
i = issue(s, "units:rt")
ok(i and i["action"] == 'Remove "ms" and read as numbers' and not issue(s, "units:w"), s["issues"])
r = run("units.csv", "describe", options=i["fix"], columns=["rt"])
close(cell(r, "Summary", "Mean"), 154.4, "mean without the unit")
same_numbers(r)
ok(issue(load("units.csv", options=i["fix"]), "units:rt")["applied"], "units applied")

# Duplicate names, one row
write("dups.csv", "x,x, y,y \n1,2,3,4\n5,6,7,8\n9,10,11,12\n")
s = load("dups.csv")
ok([c["name"] for c in s["columns"]] == ["x", "x.1", "y", "y.1"] and '"x", "y"' in issue(s, "duplicates")["message"], s)
write("one.csv", "a,b\n1,2\n")
ok(issue(load("one.csv"), "rows")["message"] == "The file has only 1 row of data, too few for most tests.", load("one.csv")["issues"])

# Load options are a strict whitelist
for bad in ({"sep": ";"}, {"decimal": ";"}, {"header": -1}, {"header": 101}, {"header": True}, {"skip": "2"},
            {"thousands": "."}, {"missing": {"a": [float("inf")]}}, {"missing": {"a": []}}, {"missing": {"a": list(range(11))}},
            {"missing": {"a": ["x" * 21]}}, {"missing": {"a": [True]}}, {"missing": ["a"]}, {"units": {"a": "m2"}},
            {"units": {"a": "m s"}}, {"units": {"a": "x" * 11}}, {"units": {"": "ms"}}, ["header"]):
    ok(load("sleep.csv", options=bad).get("error") == "Those file options are not valid.", f"accepted {bad}")
ok(load("sleep.csv", options={"missing": {"extra": [-9.5, "n.a."]}, "units": {"extra": "°C"}, "decimal": "."}).get("rows") == 20, "valid options")

# Column names and codes in the options can't inject code into the saved script either
for col in (EVIL, "a'+print('INJ' + 'ECTED')+'"):
    write("evilopts.csv", csv_of({col: [1, 2, 3, 4, 5, 6, 999, 8], "u": [f"{v} ms" for v in range(8)]}))
    r = run("evilopts.csv", "describe", options={"missing": {col: [999, "'+x+'"]}, "units": {"u": "'\\"}}, columns=[col])
    ok(r.get("code", "").startswith("# -*- coding: utf-8 -*-\n") and r["code"].isascii(), "options in the script stay ASCII")
    if "code" not in r:
        continue
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(r["code"].encode("utf-8"), "saved_script.py", "exec"), {"__name__": "__main__"})
    ok("INJECTED" not in buf.getvalue(), f"saved script ran code from the options: {buf.getvalue()[:300]}")
    same_numbers(r)

# Normality: what to do next, for one column, two groups and three or more
r = run("teeth.csv", "normality", column="len")
ok("a one-sample t-test, fits" in r["summary"], r["summary"])
r = run("sleep.csv", "normality", column="extra", group="drug")
ok("Both groups look roughly normal, so an independent t-test fits." in r["summary"], r["summary"])
r = run("plants.csv", "normality", column="weight", group="group")
ok("All groups look roughly normal, so a one-way ANOVA fits." in r["summary"], r["summary"])
write("skewed.csv", csv_of({"v": [1, 1, 1, 1, 2, 1, 1, 30, 1, 2, 5, 6, 7, 5, 6, 8, 7, 6], "g": ["a"] * 9 + ["b"] * 9}))
r = run("skewed.csv", "normality", column="v", group="g")
ok("1 of 2 groups does not look" in r["summary"] and "Mann-Whitney U test may suit better" in r["summary"], r["summary"])
r = run("big.csv", "normality", column="v")
ok(sum("only approximate" in w for w in r["warnings"]) == 1, r["warnings"])

# Grammar, and an ID used as a predictor
r = run("messy.csv", "describe", columns=["score"])
ok('1 of the values in "score" is not a number; it was treated as missing.' in r["warnings"], r["warnings"])
r = run("sleep.csv", "linear_regression", outcome="extra", predictors=["id"])
ok(any('"id" has a different value on every row, like an ID' in w for w in r["warnings"]), r["warnings"])
r = run("cars.csv", "linear_regression", outcome="dist", predictors=["speed"])
ok(not any("like an ID" in w for w in r["warnings"]), r["warnings"])

covered = {"describe", "frequencies", "normality", "t_one_sample", "t_independent", "t_paired", "mann_whitney",
           "wilcoxon", "anova_oneway", "anova_twoway", "kruskal", "chi_square", "correlation",
           "linear_regression", "logistic_regression"}
ok(covered == set(TESTS), f"every TestId has a function: {covered ^ set(TESTS)}")  # noqa: F821

print(f"{CHECKS[0]} checks, {len(FAILS)} failed")
for f in FAILS:
    print("FAIL:", f)
RESULT = len(FAILS)
