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


def load(name, sheet=None):
    out, _ = engine_load(name, name, sheet)  # noqa: F821
    return json.loads(out)


def run(name, test, sheet=None, **params):
    """Load and run, check the xlsx and the saved script, and return the result."""
    shape_ = load(name, sheet)
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
# ---- more tests (cross-checked against scipy / statsmodels called directly, or known values) ----
import numpy as np
import scipy.stats as sps
import statsmodels.api as sm_
import statsmodels.formula.api as smf_
from statsmodels.stats.anova import AnovaRM, anova_lm
from statsmodels.stats.oneway import anova_oneway as sm_welch

rng = np.random.default_rng(7)
ga, gb, gc = rng.normal(10, 1, 12), rng.normal(12, 3, 12), rng.normal(11, 6, 12)
grp = ["a"] * 12 + ["b"] * 12 + ["c"] * 12
write("three.csv", csv_of({"y": list(ga) + list(gb) + list(gc), "g": grp}))

# Levene (median-centred = Brown-Forsythe) and mean-centred
r = run("three.csv", "levene", outcome="y", group="g")
ref = sps.levene(ga, gb, gc, center="median")
close(cell(r, "Levene's test", "F"), ref.statistic, "Brown-Forsythe F")
close(cell(r, "Levene's test", "p"), ref.pvalue, "Brown-Forsythe p")
r = run("three.csv", "levene", outcome="y", group="g", center="mean")
close(cell(r, "Levene's test", "F"), sps.levene(ga, gb, gc, center="mean").statistic, "Levene F")

# Welch's ANOVA against statsmodels
r = run("three.csv", "welch_anova", outcome="y", group="g")
ref = sm_welch([ga, gb, gc], use_var="unequal")
close(cell(r, "Welch's ANOVA", "F"), ref.statistic, "Welch ANOVA F")
close(cell(r, "Welch's ANOVA", "df 2"), ref.df_denom, "Welch ANOVA df2")
close(cell(r, "Welch's ANOVA", "p"), ref.pvalue, "Welch ANOVA p")

# Kolmogorov-Smirnov
write("two.csv", csv_of({"y": list(ga) + list(gb), "g": ["a"] * 12 + ["b"] * 12}))
r = run("two.csv", "ks_two_sample", outcome="y", group="g")
ref = sps.ks_2samp(ga, gb)
close(cell(r, "Kolmogorov-Smirnov", "D"), ref.statistic, "KS D")
close(cell(r, "Kolmogorov-Smirnov", "p"), ref.pvalue, "KS p")
error("three.csv", "ks_two_sample", "exactly two groups", outcome="y", group="g")

# Binomial: R binom.test(7, 10): p = 0.3438, 95% CI 0.3475471 0.9332605
write("coin.csv", csv_of({"r": ["H"] * 7 + ["T"] * 3}))
r = run("coin.csv", "binomial", column="r", success="H", p0=0.5)
close(cell(r, "Binomial test", "p"), 0.34375, "binomial p")
close(cell(r, "Binomial test", "95% CI low"), 0.3475471, "binomial CI low")
close(cell(r, "Binomial test", "95% CI high"), 0.9332605, "binomial CI high")
error("coin.csv", "binomial", "no \"X\"", column="r", success="X")

# Goodness of fit: counts 20/30/50 give chi-square 14 on 2 df, p = exp(-7)
write("gof.csv", csv_of({"c": ["a"] * 20 + ["b"] * 30 + ["c"] * 50}))
r = run("gof.csv", "gof_chi_square", column="c")
close(cell(r, "Chi-square goodness of fit", "χ²"), 14.0, "gof chi-square")
close(cell(r, "Chi-square goodness of fit", "p"), math.exp(-7), "gof p", tol=1e-3)

# McNemar (Agresti's approval ratings: 794, 86, 150, 570): corrected chi-square (|86-150|-1)^2/236
first = ["y"] * 794 + ["y"] * 86 + ["n"] * 150 + ["n"] * 570
second = ["y"] * 794 + ["n"] * 86 + ["y"] * 150 + ["n"] * 570
write("mcn.csv", csv_of({"t1": first, "t2": second}))
r = run("mcn.csv", "mcnemar", first="t1", second="t2")
close(cell(r, "McNemar's test", "Statistic"), 63**2 / 236, "McNemar chi-square")
ok(cell(r, "McNemar's test", "p") < 0.001, "McNemar p")

# Friedman
m = rng.normal(0, 1, (15, 3)) + np.array([0, 0.5, 1.2])
write("fr.csv", csv_of({"t1": m[:, 0], "t2": m[:, 1], "t3": m[:, 2]}))
r = run("fr.csv", "friedman", columns=["t1", "t2", "t3"])
ref = sps.friedmanchisquare(m[:, 0], m[:, 1], m[:, 2])
close(cell(r, "Friedman test", "χ²"), ref.statistic, "Friedman chi-square")
close(cell(r, "Friedman test", "p"), ref.pvalue, "Friedman p")

# Repeated-measures ANOVA against statsmodels AnovaRM
r = run("fr.csv", "anova_repeated", columns=["t1", "t2", "t3"])
long = pd.DataFrame({"s": np.tile(np.arange(15), 3), "t": np.repeat(["t1", "t2", "t3"], 15), "v": m.T.ravel()})
ref = AnovaRM(long, "v", "s", within=["t"]).fit().anova_table
close(cell(r, "Repeated-measures ANOVA", "F"), ref["F Value"].iloc[0], "RM ANOVA F")
close(cell(r, "Repeated-measures ANOVA", "p"), ref["Pr > F"].iloc[0], "RM ANOVA p")
eps = cell(r, "Repeated-measures ANOVA", "df", row=2) / 2
ok(0.5 - 1e-9 <= eps <= 1 + 1e-9, "Greenhouse-Geisser epsilon in range")
two_m = run("fr.csv", "anova_repeated", columns=["t1", "t2"])
tt = sps.ttest_rel(m[:, 0], m[:, 1])
close(cell(two_m, "Repeated-measures ANOVA", "F"), tt.statistic**2, "RM ANOVA with two measurements equals paired t squared")

# ANCOVA against statsmodels (type II sums of squares)
x = rng.normal(50, 10, 36)
y = 2 + 0.3 * x + np.array([0] * 12 + [3] * 12 + [5] * 12) + rng.normal(0, 2, 36)
write("anc.csv", csv_of({"y": y, "g": grp, "x": x}))
r = run("anc.csv", "ancova", outcome="y", group="g", covariates=["x"])
ref = anova_lm(smf_.ols("y ~ C(g) + x", data=pd.DataFrame({"y": y, "g": grp, "x": x})).fit(), typ=2)
close(cell(r, "ANCOVA", "F", row=0), ref.loc["C(g)", "F"], "ANCOVA group F")
close(cell(r, "ANCOVA", "p", row=0), ref.loc["C(g)", "PR(>F)"], "ANCOVA group p")
close(cell(r, "ANCOVA", "F", row=1), ref.loc["x", "F"], "ANCOVA covariate F")
error("anc.csv", "ancova", "different columns", outcome="y", group="x", covariates=["x"])

# Partial correlation: r_xy.z = (r_xy - r_xz r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))
z = rng.normal(0, 1, 60)
px, py = z + rng.normal(0, 1, 60), z + rng.normal(0, 1, 60)
write("part.csv", csv_of({"x": px, "y": py, "z": z}))
r = run("part.csv", "partial_correlation", x="x", y="y", controls=["z"])
rxy, rxz, ryz = np.corrcoef(px, py)[0, 1], np.corrcoef(px, z)[0, 1], np.corrcoef(py, z)[0, 1]
close(cell(r, "Partial correlation", "r"), (rxy - rxz * ryz) / math.sqrt((1 - rxz**2) * (1 - ryz**2)), "partial r")
close(cell(r, "Partial correlation", "df"), 57, "partial df")

# Cohen's kappa: [[20, 5], [10, 15]] gives po = .7, pe = .5, kappa = .4
a1 = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
a2 = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
write("kap.csv", csv_of({"r1": a1, "r2": a2}))
r = run("kap.csv", "cohens_kappa", rater1="r1", rater2="r2")
close(cell(r, "Agreement", "Cohen's κ"), 0.4, "kappa")
close(cell(r, "Agreement", "Observed agreement"), 0.7, "kappa po")
close(cell(r, "Agreement", "Expected by chance"), 0.5, "kappa pe")

# Cronbach's alpha: k/(k-1) * (1 - trace(C) / sum(C)); identical items give 1
items = rng.normal(0, 1, (40, 1)) + rng.normal(0, 0.8, (40, 4))
write("scale.csv", csv_of({f"i{j}": items[:, j] for j in range(4)}))
r = run("scale.csv", "cronbach_alpha", columns=["i0", "i1", "i2", "i3"])
C = np.cov(items, rowvar=False)
close(cell(r, "Reliability", "Cronbach's α"), 4 / 3 * (1 - np.trace(C) / C.sum()), "alpha")
write("same.csv", csv_of({"a": [1, 2, 3, 4, 5], "b": [1, 2, 3, 4, 5]}))
close(cell(run("same.csv", "cronbach_alpha", columns=["a", "b"]), "Reliability", "Cronbach's α"), 1.0, "alpha of identical items")

# PCA: two perfectly correlated columns give eigenvalues 2 and 0 and loadings of 1/sqrt(2) x sqrt(2) = 1
write("pc.csv", csv_of({"a": [1, 2, 3, 4, 5, 6], "b": [2, 4, 6, 8, 10, 12], "c": [6, 1, 5, 2, 4, 3]}))
r = run("pc.csv", "pca", columns=["a", "b"])
close(cell(r, "Components", "Eigenvalue", row=0), 2.0, "PCA eigenvalue 1")
close(cell(r, "Components", "Eigenvalue", row=1), 0.0, "PCA eigenvalue 2", tol=1e-6)
close(cell(r, "Loadings", "PC1", row=0), 1.0, "PCA loading", tol=1e-6)
r = run("pc.csv", "pca", columns=["a", "b", "c"])
close(sum(row[1] for row in table(r, "Components")["rows"]), 3.0, "eigenvalues sum to the number of columns")

# one table as its own workbook
import openpyxl as _xl

wb_bytes = engine_table_xlsx(  # noqa: F821
    json.dumps({"title": "Score by arm", "summary": "S", "n": 6, "file": "my data.csv"}),
    json.dumps({"title": "Group means", "columns": ["Group", "Mean"], "rows": [["A", 1.5], ["=1+1", None]]}),
)
ok(wb_bytes[1][:2] == b"PK", "table workbook is a zip")
wb = _xl.load_workbook(io.BytesIO(wb_bytes[1]))
ok(wb.sheetnames == ["Summary", "Group means"], f"table workbook sheets: {wb.sheetnames}")
ok(wb["Group means"]["B3"].value == 1.5 and wb["Group means"]["A4"].data_type == "s", "table workbook cells")
ok(any(c.value == "my data.csv" for row in wb["Summary"].iter_rows() for c in row), "table workbook names the file")
ok("error" in json.loads(engine_table_xlsx("{}", "{}")[0]), "table workbook refuses a bad table")  # noqa: F821

# the data grid's rows
write("grid.csv", "a,b\n1,x\n2,\n3,z\n")
load("grid.csv")
page = json.loads(engine_rows(1, 5)[0])  # noqa: F821
ok(page["total"] == 3 and page["offset"] == 1, "grid: total and offset")
ok(page["rows"] == [[2, None], [3, "z"]], "grid: rows with a blank as None")
ok(json.loads(engine_rows(0, 10000)[0])["rows"][0] == [1, "x"], "grid: first row")  # noqa: F821

ok(json.loads(engine_load("missing.csv", "missing.csv")[0]).get("error", "").startswith("Something went wrong"), "missing file")  # noqa: F821
write("empty.csv", "")
ok(load("empty.csv").get("error") == "The file is empty.", "empty file")
write("notes.docx", "hello")
ok("CSV, TSV, TXT or XLSX" in load("notes.docx").get("error", ""), "unknown type")
write("header.csv", "a,b\n")
ok(load("header.csv").get("error") == "The file has no rows of data.", "header only")

covered = {"describe", "frequencies", "normality", "t_one_sample", "t_independent", "t_paired", "mann_whitney",
           "wilcoxon", "anova_oneway", "anova_twoway", "kruskal", "chi_square", "correlation",
           "linear_regression", "logistic_regression", "levene", "welch_anova", "ks_two_sample", "binomial",
           "gof_chi_square", "mcnemar", "friedman", "anova_repeated", "ancova", "partial_correlation",
           "cohens_kappa", "cronbach_alpha", "pca"}
ok(covered == set(TESTS), f"every TestId has a function: {covered ^ set(TESTS)}")  # noqa: F821

print(f"{CHECKS[0]} checks, {len(FAILS)} failed")
for f in FAILS:
    print("FAIL:", f)
RESULT = len(FAILS)
