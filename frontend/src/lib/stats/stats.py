"""Statistics for labbenchos, run in the browser by Pyodide (see worker.ts).

One function per test in contract.ts TESTS, named by its TestId and taking its params by key. Each
returns a plain dict (title, summary, tables, charts, warnings, n). The engine_* functions at the end
are the worker's entry points. Saved scripts copy a test function and the helpers it uses out of this
file (make_code), so tests import scipy and statsmodels inside themselves.
"""

import csv
import io
import math

import numpy as np
import pandas as pd

MAX_GROUPS = 20  # more distinct values than this is not a grouping column
TOP_VALUES = 50  # longest frequency list
CHART_CAP = 5000  # most raw values in one chart


class UserError(Exception):
    """A problem with the file or the choices, in plain words that are safe to show."""


# Reading files ----------------------------------------------------------------------------------


def read_data(path, sheet=None, header=0, skip=0, decimal=".", thousands=None, missing=None, units=None):
    """Read a CSV, TSV, TXT or XLSX file into a table.

    header: the row with the column names (0 is the first); rows above it are left out.
    skip: how many rows right under the column names to leave out.
    decimal, thousands: how numbers are written in a text file ("," and "." for 1.234,5).
    missing: values to treat as missing, by column. units: a unit to remove, by column ("ms" in "12 ms").
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    with open(path, "rb") as f:
        data = f.read()
    if not data.strip(b"\x00\t\n\r \xef\xbb\xbf\xff\xfe"):
        raise UserError("The file is empty.")
    rows = None
    if header or skip:
        rows = lambda i: i < header or header < i <= header + skip  # noqa: E731
    if ext in ("xlsx", "xlsm"):
        try:
            book = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
        except Exception:
            raise UserError("This workbook could not be opened. Check it is an Excel .xlsx file.")
        if sheet is None:
            sheet = book.sheet_names[0]
        elif sheet not in book.sheet_names:
            raise UserError(f'The workbook has no sheet called "{sheet}".')
        df = book.parse(sheet, skiprows=rows)
    elif ext == "xls":
        raise UserError("Old Excel files (.xls) can't be read here. Save it as .xlsx or CSV first.")
    elif ext in ("csv", "tsv", "txt", ""):
        text = _decode(data)
        sep = "\t" if ext == "tsv" else _sniff(text)
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, skiprows=rows, decimal=decimal, thousands=thousands)
        except pd.errors.EmptyDataError:
            raise UserError("The file has no data in it.")
        except pd.errors.ParserError:
            raise UserError(
                "The file could not be read as a table. Check every row has the same number of columns."
            )
    else:
        raise UserError("This kind of file can't be read here. Use CSV, TSV, TXT or XLSX.")
    names = []
    for name in (str(c).strip() for c in df.columns):
        base, i = name, 1
        while name in names:  # " x" and "x" are the same name once stripped
            name, i = f"{base}.{i}", i + 1
        names.append(name)
    df.columns = names
    # Units first, so a missing code like 999 matches once "999 ms" is a number.
    for col, unit in (units or {}).items():
        if col in df.columns:
            text = df[col].map(lambda v: v if pd.isna(v) else str(v).strip().removesuffix(unit).strip())
            df[col] = pd.to_numeric(text, errors="coerce")
    for col, codes in (missing or {}).items():
        if col in df.columns:
            s = df[col]
            hit = pd.to_numeric(s, errors="coerce").isin([c for c in codes if not isinstance(c, str)])
            hit |= s.astype(str).str.strip().isin([c for c in codes if isinstance(c, str)])
            df[col] = s.mask(hit)
    df = df.dropna(how="all")
    df = df.loc[:, [not (c.startswith("Unnamed:") and df[c].isna().all()) for c in df.columns]]
    if df.empty:
        raise UserError("The file has no rows of data.")
    return df.reset_index(drop=True)


def _decode(data):
    """Bytes to text: UTF-16 (with a byte order mark, or many zero bytes), else UTF-8, else Latin-1."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    head = data[:4096]
    if head.count(0) > len(head) // 4:
        le = head[1::2].count(0) > head[::2].count(0)
        return data.decode("utf-16-le" if le else "utf-16-be", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _sniff(text):
    sample = text[:65536]
    if len(text) > len(sample) and "\n" in sample:
        sample = sample[: sample.rindex("\n")]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _present(s):
    """The non-missing values of a column, with blank text treated as missing."""
    s = s.dropna()
    if not (pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s)):
        s = s.astype(str).str.strip()
        s = s[s != ""]
    return s


def _kind(s, present):
    if len(present) == 0:
        return "text"
    if pd.api.types.is_bool_dtype(s):
        return "categorical"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if not pd.api.types.is_datetime64_any_dtype(s):
        if pd.to_numeric(present, errors="coerce").notna().mean() >= 0.8:
            return "numeric"
    distinct = present.nunique()
    return "categorical" if distinct <= MAX_GROUPS and distinct < len(present) else "text"


def shape(df):
    """What the screens need to know about each column."""
    columns = []
    for name in df.columns:
        s = df[name]
        present = _present(s)
        sample = list(dict.fromkeys(present.iloc[:200].tolist()))[:5]
        columns.append(
            {
                "name": name,
                "kind": _kind(s, present),
                "missing": int(len(s) - len(present)),
                "distinct": int(present.nunique()),
                "sample": sample,
            }
        )
    return {"rows": int(len(df)), "columns": columns}


# Helpers ----------------------------------------------------------------------------------------


def _col(df, col):
    if not isinstance(col, str) or col not in df.columns:
        raise UserError(f'There is no column called "{col}" in the file.')
    return df[col]


def _list(value):
    return [value] if isinstance(value, str) else list(value or [])


def _numbers(df, col, warn):
    """A column as numbers. Values that are not numbers become missing, with a warning."""
    s = _col(df, col)
    if pd.api.types.is_datetime64_any_dtype(s):
        raise UserError(f'"{col}" holds dates, not numbers. Pick a column of numbers.')
    if pd.api.types.is_bool_dtype(s) or pd.api.types.is_numeric_dtype(s):
        num = s.astype(float)
    else:
        present = _present(s)
        parsed = pd.to_numeric(present, errors="coerce")
        bad = int(parsed.isna().sum())
        num = parsed.reindex(s.index).astype(float)
        if bad == 1 and parsed.notna().any():
            warn.append(f'1 of the values in "{col}" is not a number; it was treated as missing.')
        elif bad and parsed.notna().any():
            warn.append(f'{bad} of the values in "{col}" are not numbers; they were treated as missing.')
    num = num.replace([np.inf, -np.inf], np.nan)
    if num.notna().sum() == 0:
        raise UserError(f'"{col}" has no numbers in it. Pick a column of numbers.')
    return num


def _labels(df, col):
    """A column as group names (text), with blanks as missing. 1.0 becomes "1"."""
    s = _col(df, col)
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return s.map(lambda v: None if pd.isna(v) else f"{v:g}" if v != int(v) else str(int(v)))
    return s.map(lambda v: None if pd.isna(v) or str(v).strip() == "" else str(v).strip())


def _key(v):
    """Sort group names as numbers when they look like numbers."""
    try:
        return (0, float(v), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(v))


def _levels(labels, col, at_most=MAX_GROUPS):
    levels = sorted(labels.dropna().unique(), key=_key)
    if len(levels) > at_most:
        raise UserError(
            f'"{col}" has {len(levels)} different values. Pick a column with {at_most} groups or fewer.'
        )
    return levels


def _complete(frame, warn):
    """Keep only rows with a value in every column (listwise deletion)."""
    out = frame.dropna()
    gone = len(frame) - len(out)
    if gone:
        why = "it had a missing value" if gone == 1 else "they had missing values"
        warn.append(f"Left out {gone} of {len(frame)} rows because {why}.")
    return out


ID_NAMES = {
    "id", "record_id", "participant", "participant_id", "participantid", "subject", "subject_id",
    "subjectid", "subj", "pid", "ppid", "ppt",
}


def _repeated(df, rows):
    """A sentence when the rows look like repeated measures of the same people, else None."""
    for c in df.columns:
        if c.strip().lower().replace(" ", "_").replace("-", "_") in ID_NAMES:
            ids = _labels(df, c).loc[rows].dropna()
            if ids.duplicated().any():
                return (
                    f'"{c}" repeats ({len(ids)} rows, {ids.nunique()} different values), so some '
                    "people have more than one row."
                )
            return None
    for c in ("redcap_event_name", "redcap_repeat_instrument"):
        if c in df.columns and df.loc[rows, c].notna().any():
            return f'The file has "{c}", so some people may have more than one row.'
    return None


def _repeat_warn(df, rows, warn):
    said = _repeated(df, rows)
    if said:
        warn.append(f"{said} This test assumes each row is a different person, so its p-value may be too small.")


def _id_warn(df, col, rows, warn, role):
    """Warn when a column used as groups or a predictor has a different value on every row, like an ID."""
    v = _col(df, col).loc[rows].dropna()
    if len(v) < 5 or v.nunique() < len(v):
        return
    named = col.strip().lower().replace(" ", "_").replace("-", "_") in ID_NAMES
    if pd.api.types.is_numeric_dtype(v) and not pd.api.types.is_bool_dtype(v):
        n = v.astype(float)
        if not named and not ((n == n.round()).all() and n.max() - n.min() == len(n) - 1):
            return  # distinct measurements, not row numbers
    warn.append(f'"{col}" has a different value on every row, like an ID, so it may not mean much as {role}.')


def _named_list(names):
    names = [f'"{n}"' for n in names]
    return ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")


def _two_groups(df, outcome, group, warn, test, other):
    frame = _complete(pd.DataFrame({"y": _numbers(df, outcome, warn), "g": _labels(df, group)}), warn)
    levels = _levels(frame["g"], group, at_most=10**9)
    if len(levels) != 2:
        found = f" ({_named_list(levels)})" if levels else ""
        hint = f" Use {other} for three or more groups." if len(levels) > 2 else ""
        raise UserError(
            f'The {test} needs exactly two groups, but "{group}" has {len(levels)}{found}.{hint}'
        )
    groups = {k: frame.loc[frame["g"] == k, "y"].to_numpy(float) for k in levels}
    for k, v in groups.items():
        if len(v) < 2:
            raise UserError(f'Group "{k}" has {len(v)} value; each group needs at least 2.')
    _repeat_warn(df, frame.index, warn)
    return frame, groups


def _k_groups(df, outcome, group, warn, test):
    frame = _complete(pd.DataFrame({"y": _numbers(df, outcome, warn), "g": _labels(df, group)}), warn)
    levels = _levels(frame["g"], group)
    if len(levels) < 2:
        raise UserError(f'The {test} needs at least two groups, but "{group}" has {len(levels)}.')
    if len(levels) == 2:
        warn.append("There are only two groups; a t-test or Mann-Whitney U answers the same question.")
    groups = {k: frame.loc[frame["g"] == k, "y"].to_numpy(float) for k in levels}
    small = [k for k, v in groups.items() if len(v) < 2]
    if small:
        raise UserError(f"Each group needs at least 2 values; {_named_list(small)} has fewer.")
    _repeat_warn(df, frame.index, warn)
    return frame, groups


def _paired(df, before, after, warn):
    if before == after:
        raise UserError("Pick two different columns for the two measurements.")
    frame = _complete(
        pd.DataFrame({"x": _numbers(df, before, warn), "y": _numbers(df, after, warn)}), warn
    )
    if len(frame) < 2:
        raise UserError("There need to be at least 2 rows with both measurements.")
    return frame["x"].to_numpy(float), frame["y"].to_numpy(float)


def _normal_warn(v, what, warn, other):
    from scipy import stats

    if 3 <= len(v) < 30 and np.ptp(v) > 0 and stats.shapiro(v).pvalue < 0.05:
        warn.append(
            f"{what} do not look normally distributed (Shapiro-Wilk p < .05) and the sample is "
            f"small, so the {other} may suit better."
        )


def _mean_ci(v):
    from scipy import stats

    v = np.asarray(v, float)
    m = float(np.mean(v))
    if len(v) < 2:
        return m, None, None
    h = float(stats.t.ppf(0.975, len(v) - 1) * np.std(v, ddof=1) / math.sqrt(len(v)))
    return m, m - h, m + h


def _hedges(d, dof):
    return d * (1 - 3 / (4 * dof - 1))


def _ci95(est, se):
    return est - 1.959964 * se, est + 1.959964 * se


def _strength(r):
    r = abs(r)
    return "very weakly" if r < 0.1 else "weakly" if r < 0.3 else "moderately" if r < 0.5 else "strongly"


# Formatting: APA style numbers for the summaries -----------------------------------------------


def _f(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def _nz(x, d=2):
    """No leading zero, for numbers that can't go above 1 (p, r, R², eta²)."""
    s = _f(x, d)
    return s.replace("0.", ".", 1) if s.lstrip("-").startswith("0.") else s


def _p(p):
    return "p < .001" if p < 0.001 else f"p = {_nz(p, 3)}"


def _dof(x):
    return f"{x:.0f}" if abs(x - round(x)) < 1e-9 else f"{x:.1f}"


def _r(x):
    """Round a number for a table."""
    if x is None or isinstance(x, (str, bool, np.bool_)):
        return x
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    if not np.isfinite(x):
        return None
    return round(x, 4) if x == 0 or abs(x) >= 0.001 else float(f"{x:.3g}")


def _table(title, columns, rows, note=None):
    t = {"title": title, "columns": columns, "rows": [[_r(v) for v in row] for row in rows]}
    if note:
        t["note"] = note
    return t


def _result(title, summary, tables, charts, warn, n):
    return {
        "title": title,
        "summary": summary,
        "tables": tables,
        "charts": charts,
        "warnings": warn,
        "n": int(n),
    }


# Charts: data for the screens to draw ----------------------------------------------------------


def _sample(v, cap):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) > cap:
        v = np.random.default_rng(0).choice(v, cap, replace=False)
    return [float(x) for x in v]


def _hist(title, label, groups):
    cap = CHART_CAP // max(len(groups), 1)
    return {
        "kind": "histogram",
        "title": title,
        "xLabel": label,
        "groups": [{"name": str(k), "values": _sample(v, cap)} for k, v in groups.items()],
    }


def _box(title, label, groups):
    cap = CHART_CAP // max(len(groups), 1)
    return {
        "kind": "box",
        "title": title,
        "yLabel": label,
        "groups": [{"name": str(k), "values": _sample(v, cap)} for k, v in groups.items()],
    }


def _mean_bars(title, label, groups):
    bars = []
    for k, v in groups.items():
        m, lo, hi = _mean_ci(v)
        bar = {"name": str(k), "value": m}
        if lo is not None:
            bar.update(low=lo, high=hi)
        bars.append(bar)
    return {"kind": "bar", "title": title + " (with 95% CI)", "yLabel": label, "bars": bars}


def _scatter(title, x_label, y_label, x, y, line=None):
    pts = np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    if len(pts) > CHART_CAP:
        pts = pts[np.random.default_rng(0).choice(len(pts), CHART_CAP, replace=False)]
    chart = {
        "kind": "scatter",
        "title": title,
        "xLabel": x_label,
        "yLabel": y_label,
        "points": [[float(a), float(b)] for a, b in pts],
    }
    if line is not None:
        chart["line"] = {"slope": float(line[0]), "intercept": float(line[1])}
    return chart


# Tests: one function per TestId in contract.ts --------------------------------------------------


def describe(df, columns, group=None):
    """Count, mean, SD, median, range and missing values, optionally split by group."""
    warn = []
    columns = list(dict.fromkeys(_list(columns)))
    if not columns:
        raise UserError("Pick at least one column.")
    data = pd.DataFrame({c: _numbers(df, c, warn) for c in columns})
    parts = {None: data}
    if group:
        g = _labels(df, group)
        if g.isna().any():
            warn.append(f'Left out {int(g.isna().sum())} of {len(g)} rows with no value in "{group}".')
        data, g = data[g.notna()], g[g.notna()]
        _id_warn(df, group, g.index, warn, "groups")
        parts = {k: data[g == k] for k in _levels(g, group)}
    rows = []
    for c in columns:
        for k, part in parts.items():
            v = part[c].dropna()
            rows.append(
                [c]
                + ([k] if group else [])
                + [len(v), int(part[c].isna().sum()), v.mean(), v.std(), v.median(), v.min(), v.max()]
            )
    head = ["Column"] + (["Group"] if group else [])
    table = _table(
        "Summary statistics", head + ["N", "Missing", "Mean", "SD", "Median", "Min", "Max"], rows
    )
    charts = []
    for c in columns[:4]:
        groups = {(k if group else c): part[c].dropna() for k, part in parts.items()}
        charts.append(_hist(f'Distribution of "{c}"', c, groups))
        if group:
            charts.append(_box(f'"{c}" by "{group}"', c, groups))
    if group:
        summary = (
            f'Summary statistics for {len(columns)} column{"s" if len(columns) > 1 else ""}, '
            f'split by "{group}" into {len(parts)} groups.'
        )
    else:
        lines = []
        for c in columns[:3]:
            v = data[c].dropna()
            lines.append(
                f'"{c}": M = {_f(v.mean())}, SD = {_f(v.std())}, Mdn = {_f(v.median())}, '
                f"range {_f(v.min())} to {_f(v.max())}, n = {len(v)}."
            )
        if len(columns) > 3:
            lines.append(f"The table has the other {len(columns) - 3} columns.")
        summary = " ".join(lines)
    return _result("Summary statistics", summary, [table], charts, warn, len(data))


def frequencies(df, columns):
    """How often each value appears; two columns give a cross-table."""
    warn = []
    columns = list(dict.fromkeys(_list(columns)))
    if not columns:
        raise UserError("Pick at least one column.")
    if len(columns) == 2:
        a, b = columns
        frame, table = _crosstab(df, a, b, warn)
        pct = table.div(table.sum(axis=1), axis=0) * 100
        tables = [
            _count_table(f'Counts: "{a}" by "{b}"', table, a, b),
            _table(
                f'Row percentages: "{a}" by "{b}"',
                [f"{a} / {b}"] + [str(c) for c in table.columns],
                [[k] + list(pct.loc[k]) for k in table.index],
            ),
        ]
        top = table.stack().idxmax()
        summary = (
            f'Cross-table of "{a}" ({len(table.index)} values) by "{b}" ({len(table.columns)} '
            f'values) over {len(frame)} rows. The most common pair is "{top[0]}" with "{top[1]}" '
            f"({int(table.loc[top])} rows)."
        )
        return _result(f'Counts: "{a}" by "{b}"', summary, tables, [], warn, len(frame))
    tables, charts, lines = [], [], []
    for c in columns:
        s = _labels(df, c)
        counts = s.value_counts()
        total, valid = len(s), int(counts.sum())
        missing = total - valid
        if valid >= 10 and counts.max() == 1:
            tables.append(
                _table(
                    f'Counts: "{c}"',
                    ["Value", "Count", "Percent"],
                    [["(all different)", valid, 100 * valid / total]]
                    + ([["Missing", missing, 100 * missing / total]] if missing else []),
                    note="Every value is different (like an ID or free text), so they are not listed.",
                )
            )
            lines.append(f'Every value in "{c}" is different ({valid} values).')
            continue
        note = None
        if len(counts) > MAX_GROUPS:
            shown = counts[counts > 1]
            shown = shown.iloc[sorted(range(len(shown)), key=lambda i: (-shown.iloc[i], _key(shown.index[i])))]
            shown = shown.head(TOP_VALUES)
            note = (
                f"Showing the {len(shown)} most common of {len(counts)} different values. "
                "Values that appear only once are not listed."
            )
        else:
            shown = counts.reindex(sorted(counts.index, key=_key))
        rows = [[k, int(n), 100 * n / total, 100 * n / valid] for k, n in shown.items()]
        if missing:
            rows.append(["Missing", missing, 100 * missing / total, None])
        rows.append(["Total", total, 100.0, None])
        tables.append(
            _table(f'Counts: "{c}"', ["Value", "Count", "Percent", "Valid percent"], rows, note)
        )
        if len(counts) <= MAX_GROUPS:
            charts.append(
                {
                    "kind": "bar",
                    "title": f'Counts of "{c}"',
                    "yLabel": "Count",
                    "bars": [{"name": str(k), "value": int(n)} for k, n in shown.items()],
                }
            )
        if valid:
            k = counts.idxmax()
            lines.append(
                f'"{c}" has {len(counts)} different value{"s" if len(counts) > 1 else ""}; the most '
                f'common is "{k}" ({int(counts[k])} of {valid}, {100 * counts[k] / valid:.1f}%).'
            )
        else:
            lines.append(f'"{c}" has no values.')
        if missing:
            lines.append(f"{missing} missing.")
    return _result("Counts and percentages", " ".join(lines), tables, charts, warn, len(df))


def _crosstab(df, a, b, warn):
    if a == b:
        raise UserError("Pick two different columns.")
    frame = _complete(pd.DataFrame({"a": _labels(df, a), "b": _labels(df, b)}), warn)
    ra, rb = _levels(frame["a"], a), _levels(frame["b"], b)
    table = pd.crosstab(frame["a"], frame["b"]).reindex(index=ra, columns=rb, fill_value=0)
    return frame, table


def _count_table(title, table, a, b):
    rows = [[k] + [int(x) for x in table.loc[k]] + [int(table.loc[k].sum())] for k in table.index]
    rows.append(["Total"] + [int(x) for x in table.sum()] + [int(table.values.sum())])
    return _table(title, [f"{a} / {b}"] + [str(c) for c in table.columns] + ["Total"], rows)


def normality(df, column, group=None):
    """Shapiro-Wilk test, skew and kurtosis."""
    from scipy import stats

    warn = []
    frame = pd.DataFrame({"x": _numbers(df, column, warn)})
    if group:
        frame["g"] = _labels(df, group)
    frame = _complete(frame, warn)
    if group:
        _id_warn(df, group, frame.index, warn, "groups")
        groups = {k: frame.loc[frame["g"] == k, "x"].to_numpy(float) for k in _levels(frame["g"], group)}
    else:
        groups = {column: frame["x"].to_numpy(float)}
    rows, failed = [], []
    for k, v in groups.items():
        w = p = skew = kurt = None
        if len(v) >= 3 and np.ptp(v) > 0:
            w, p = stats.shapiro(v)
            skew = stats.skew(v, bias=False)
            if len(v) >= 4:
                kurt = stats.kurtosis(v, bias=False)
            if p < 0.05:
                failed.append(k)
        else:
            warn.append(f'"{k}" has fewer than 3 different values, too few to test.')
        rows.append(([k] if group else []) + [len(v), np.mean(v), np.std(v, ddof=1) if len(v) > 1 else None, skew, kurt, w, p])
    if any(len(v) > 5000 for v in groups.values()):
        warn.append(
            "Above 5,000 values the Shapiro-Wilk p-value is only approximate, and with this many values "
            "even tiny departures from normal count as significant. Judge by the histogram, skew and kurtosis."
        )
    head = (["Group"] if group else []) + ["N", "Mean", "SD", "Skew", "Kurtosis", "Shapiro-Wilk W", "p"]
    table = _table("Normality", head, rows, note="Kurtosis is excess kurtosis (0 for a normal distribution).")
    charts = [_hist(f'Distribution of "{column}"', column, groups)]
    if group:
        charts.append(_box(f'"{column}" by "{group}"', column, groups))
        tested = [r for r in rows if r[-1] is not None]
        if failed:
            summary = (
                f"{len(failed)} of {len(tested)} groups {'does' if len(failed) == 1 else 'do'} not look normally distributed "
                f"(Shapiro-Wilk p < .05): {_named_list(failed)}."
            )
        else:
            summary = f"All {len(tested)} groups look normally distributed (Shapiro-Wilk p ≥ .05)."
        if len(tested) == len(groups) == 2:
            summary += (
                " So the Mann-Whitney U test may suit better than an independent t-test, especially with small groups."
                if failed else " Both groups look roughly normal, so an independent t-test fits."
            )
        elif len(tested) == len(groups) > 2:
            summary += (
                " So the Kruskal-Wallis test may suit better than a one-way ANOVA, especially with small groups."
                if failed else " All groups look roughly normal, so a one-way ANOVA fits."
            )
    else:
        _n, _m, _sd, skew, kurt, w, p = rows[0]
        if w is None:
            summary = f'"{column}" has too few different values to test.'
        else:
            looks = "does not look" if p < 0.05 else "looks"
            summary = (
                f'"{column}" {looks} normally distributed, Shapiro-Wilk W = {_nz(w)}, {_p(p)} '
                f"(skew = {_f(skew)}, kurtosis = {_f(kurt)}, n = {len(frame)})."
            )
            summary += (
                " A test that does not assume normal data, such as the Wilcoxon signed-rank test, may suit "
                "better, especially with a small sample." if p < 0.05
                else " So a test that assumes normal data, such as a one-sample t-test, fits."
            )
    return _result(f'Normality of "{column}"', summary, [table], charts, warn, len(frame))


def t_one_sample(df, column, mu=0):
    """Is the mean different from a set value?"""
    from scipy import stats

    warn = []
    try:
        mu = float(mu)
    except (TypeError, ValueError):
        raise UserError("The value to compare with must be a number.")
    x = _complete(pd.DataFrame({"x": _numbers(df, column, warn)}), warn)["x"].to_numpy(float)
    n = len(x)
    if n < 2:
        raise UserError(f'"{column}" needs at least 2 numbers for a t-test.')
    m, sd = x.mean(), x.std(ddof=1)
    if sd == 0:
        raise UserError(f'Every value in "{column}" is the same, so a t-test can\'t be run.')
    res = stats.ttest_1samp(x, mu)
    ci = res.confidence_interval()
    d = (m - mu) / sd
    d_lo, d_hi = _ci95(d, math.sqrt(1 / n + d**2 / (2 * n)))
    _normal_warn(x, "The values", warn, "Wilcoxon signed-rank test")
    tables = [
        _table("Descriptives", ["Column", "N", "Mean", "SD", "SE"], [[column, n, m, sd, sd / math.sqrt(n)]]),
        _table(
            "One-sample t-test",
            ["Compared with", "t", "df", "p", "Mean difference", "95% CI low", "95% CI high",
             "Cohen's d", "d 95% CI low", "d 95% CI high", "Hedges' g"],
            [[mu, res.statistic, res.df, res.pvalue, m - mu, ci.low - mu, ci.high - mu,
              d, d_lo, d_hi, _hedges(d, n - 1)]],
            note="The confidence interval is for the difference between the mean and the value compared with.",
        ),
    ]
    stat = f"t({_dof(res.df)}) = {_f(abs(res.statistic))}, {_p(res.pvalue)}, d = {_f(abs(d))}"
    desc = f'The mean of "{column}" (M = {_f(m)}, SD = {_f(sd)})'
    if res.pvalue < 0.05:
        summary = f"{desc} was {'higher' if m > mu else 'lower'} than {mu:g}, {stat}."
    else:
        summary = f"{desc} was not significantly different from {mu:g}, {stat}."
    charts = [_hist(f'Distribution of "{column}"', column, {column: x})]
    return _result(f'One-sample t-test: "{column}" against {mu:g}', summary, tables, charts, warn, n)


def t_independent(df, outcome, group, variant="welch"):
    """Do two separate groups differ on average? Welch's or Student's t-test."""
    from scipy import stats

    if variant not in ("welch", "student"):
        raise UserError('The version must be "welch" or "student".')
    warn = []
    frame, groups = _two_groups(df, outcome, group, warn, "independent t-test", "one-way ANOVA")
    (ka, a), (kb, b) = groups.items()
    n1, n2 = len(a), len(b)
    m1, m2, s1, s2 = a.mean(), b.mean(), a.std(ddof=1), b.std(ddof=1)
    if s1 == 0 and s2 == 0:
        raise UserError(f'Every value in "{outcome}" is the same within each group, so a t-test can\'t be run.')
    res = stats.ttest_ind(a, b, equal_var=variant == "student")
    ci = res.confidence_interval()
    sp = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp
    d_lo, d_hi = _ci95(d, math.sqrt((n1 + n2) / (n1 * n2) + d**2 / (2 * (n1 + n2))))
    lev = stats.levene(a, b, center="mean")
    if variant == "student" and lev.pvalue < 0.05:
        warn.append(
            f"The two groups' spreads differ (Levene's test {_p(lev.pvalue)}). "
            "The Welch version does not assume equal spreads."
        )
    for k, v in groups.items():
        _normal_warn(v, f'The values in "{k}"', warn, "Mann-Whitney U test")
    name = "Welch's t-test" if variant == "welch" else "Student's t-test"
    tables = [
        _table(
            "Descriptives",
            ["Group", "N", "Mean", "SD", "SE"],
            [[k, len(v), v.mean(), v.std(ddof=1), v.std(ddof=1) / math.sqrt(len(v))] for k, v in groups.items()],
        ),
        _table(
            name,
            ["t", "df", "p", f"Mean difference ({ka} − {kb})", "95% CI low", "95% CI high",
             "Cohen's d", "d 95% CI low", "d 95% CI high", "Hedges' g"],
            [[res.statistic, res.df, res.pvalue, m1 - m2, ci.low, ci.high, d, d_lo, d_hi,
              _hedges(d, n1 + n2 - 2)]],
            note="Cohen's d uses the pooled standard deviation.",
        ),
        _table("Levene's test for equal variances", ["F", "df1", "df2", "p"], [[lev.statistic, 1, n1 + n2 - 2, lev.pvalue]]),
    ]
    (khi, hi), (klo, lo) = sorted(groups.items(), key=lambda kv: -kv[1].mean())
    stat = f"t({_dof(res.df)}) = {_f(abs(res.statistic))}, {_p(res.pvalue)}, d = {_f(abs(d))}"
    describe_hi = f'"{khi}" (M = {_f(hi.mean())}, SD = {_f(hi.std(ddof=1))})'
    describe_lo = f'"{klo}" (M = {_f(lo.mean())}, SD = {_f(lo.std(ddof=1))})'
    if res.pvalue < 0.05:
        summary = f'{describe_hi} scored higher on "{outcome}" than {describe_lo}, {stat}.'
    else:
        summary = f'"{outcome}" did not differ significantly between {describe_hi} and {describe_lo}, {stat}.'
    charts = [
        _box(f'"{outcome}" by "{group}"', outcome, groups),
        _mean_bars(f'Mean "{outcome}" by "{group}"', outcome, groups),
    ]
    return _result(f'Independent t-test: "{outcome}" by "{group}"', summary, tables, charts, warn, len(frame))


def t_paired(df, before, after):
    """Did the same people change between two measurements?"""
    from scipy import stats

    warn = []
    x, y = _paired(df, before, after, warn)
    diff = y - x
    n = len(diff)
    if diff.std(ddof=1) == 0:
        raise UserError("The difference is the same for every row, so a t-test can't be run.")
    res = stats.ttest_1samp(diff, 0)
    ci = res.confidence_interval()
    dz = diff.mean() / diff.std(ddof=1)
    d_lo, d_hi = _ci95(dz, math.sqrt(1 / n + dz**2 / (2 * n)))
    _normal_warn(diff, "The differences", warn, "Wilcoxon signed-rank test")
    tables = [
        _table(
            "Descriptives",
            ["Measurement", "N", "Mean", "SD"],
            [[before, n, x.mean(), x.std(ddof=1)], [after, n, y.mean(), y.std(ddof=1)],
             [f"Difference ({after} − {before})", n, diff.mean(), diff.std(ddof=1)]],
        ),
        _table(
            "Paired t-test",
            ["t", "df", "p", "Mean difference", "95% CI low", "95% CI high",
             "Cohen's dz", "dz 95% CI low", "dz 95% CI high", "Hedges' gz"],
            [[res.statistic, res.df, res.pvalue, diff.mean(), ci.low, ci.high, dz, d_lo, d_hi, _hedges(dz, n - 1)]],
            note=f'Differences are "{after}" minus "{before}". dz is the mean difference divided by the SD of the differences.',
        ),
    ]
    stat = f"t({_dof(res.df)}) = {_f(res.statistic)}, {_p(res.pvalue)}, dz = {_f(abs(dz))}"
    change = f'from "{before}" (M = {_f(x.mean())}, SD = {_f(x.std(ddof=1))}) to "{after}" (M = {_f(y.mean())}, SD = {_f(y.std(ddof=1))})'
    if res.pvalue < 0.05:
        summary = f"Values {'rose' if diff.mean() > 0 else 'fell'} {change}, {stat}."
    else:
        summary = f"There was no significant change {change}, {stat}."
    charts = [
        _mean_bars("Mean of each measurement", "Value", {before: x, after: y}),
        _hist(f'Differences ("{after}" − "{before}")', "Difference", {"Difference": diff}),
    ]
    return _result(f'Paired t-test: "{before}" and "{after}"', summary, tables, charts, warn, n)


def mann_whitney(df, outcome, group):
    """Two separate groups, without assuming normal data."""
    from scipy import stats

    warn = []
    frame, groups = _two_groups(df, outcome, group, warn, "Mann-Whitney U test", "Kruskal-Wallis")
    (ka, a), (kb, b) = groups.items()
    res = stats.mannwhitneyu(a, b, alternative="two-sided")
    r = 2 * res.statistic / (len(a) * len(b)) - 1
    ranks = stats.rankdata(np.concatenate([a, b]))
    mean_ranks = [ranks[: len(a)].mean(), ranks[len(a):].mean()]
    tables = [
        _table(
            "Descriptives",
            ["Group", "N", "Median", "Mean rank"],
            [[k, len(v), np.median(v), mr] for (k, v), mr in zip(groups.items(), mean_ranks)],
        ),
        _table(
            "Mann-Whitney U test",
            ["U", "p", "Rank-biserial r"],
            [[res.statistic, res.pvalue, r]],
            note=f'U is for "{ka}". A positive r means "{ka}" tends to be higher than "{kb}".',
        ),
    ]
    (khi, hi), (klo, lo) = ((ka, a), (kb, b)) if r >= 0 else ((kb, b), (ka, a))
    stat = f"U = {_f(res.statistic, 1)}, {_p(res.pvalue)}, r = {_nz(abs(r))}"
    if res.pvalue < 0.05:
        summary = f'"{outcome}" tended to be higher in "{khi}" (Mdn = {_f(np.median(hi))}) than in "{klo}" (Mdn = {_f(np.median(lo))}), {stat}.'
    else:
        summary = f'"{outcome}" did not differ significantly between "{ka}" (Mdn = {_f(np.median(a))}) and "{kb}" (Mdn = {_f(np.median(b))}), {stat}.'
    charts = [_box(f'"{outcome}" by "{group}"', outcome, groups)]
    return _result(f'Mann-Whitney U: "{outcome}" by "{group}"', summary, tables, charts, warn, len(frame))


def wilcoxon(df, before, after):
    """Two measurements of the same people, without assuming normal data."""
    from scipy import stats

    warn = []
    x, y = _paired(df, before, after, warn)
    diff = y - x
    nonzero = diff[diff != 0]
    if len(nonzero) < len(diff):
        same = len(diff) - len(nonzero)
        warn.append(f"{same} {'row had' if same == 1 else 'rows had'} no change and {'was' if same == 1 else 'were'} left out of the test.")
    if len(nonzero) < 1:
        raise UserError("No row changed between the two measurements, so there is nothing to test.")
    res = stats.wilcoxon(nonzero)
    ranks = stats.rankdata(np.abs(nonzero))
    t_plus, t_minus = ranks[nonzero > 0].sum(), ranks[nonzero < 0].sum()
    r = (t_plus - t_minus) / (t_plus + t_minus)
    tables = [
        _table(
            "Descriptives",
            ["Measurement", "N", "Median"],
            [[before, len(x), np.median(x)], [after, len(y), np.median(y)],
             [f"Difference ({after} − {before})", len(diff), np.median(diff)]],
        ),
        _table(
            "Wilcoxon signed-rank test",
            ["Pairs that changed", "Sum of positive ranks", "Sum of negative ranks", "T", "p", "Rank-biserial r"],
            [[len(nonzero), t_plus, t_minus, res.statistic, res.pvalue, r]],
            note=f'Differences are "{after}" minus "{before}"; T is the smaller rank sum. A positive r means values rose.',
        ),
    ]
    stat = f"T = {_f(res.statistic, 1)}, {_p(res.pvalue)}, r = {_nz(abs(r))}"
    medians = f'"{before}" (Mdn = {_f(np.median(x))}) and "{after}" (Mdn = {_f(np.median(y))})'
    if res.pvalue < 0.05:
        summary = f"Values {'rose' if r > 0 else 'fell'} between {medians}, {stat}."
    else:
        summary = f"There was no significant change between {medians}, {stat}."
    charts = [
        _box("Each measurement", "Value", {before: x, after: y}),
        _hist(f'Differences ("{after}" − "{before}")', "Difference", {"Difference": diff}),
    ]
    return _result(f'Wilcoxon signed-rank: "{before}" and "{after}"', summary, tables, charts, warn, len(diff))


def anova_oneway(df, outcome, group):
    """Do three or more groups differ on average? With Tukey HSD comparisons."""
    from scipy import stats

    warn = []
    frame, groups = _k_groups(df, outcome, group, warn, "one-way ANOVA")
    names, values = list(groups), list(groups.values())
    allv = frame["y"].to_numpy(float)
    n, k = len(allv), len(values)
    ss_total = ((allv - allv.mean()) ** 2).sum()
    ss_between = sum(len(v) * (v.mean() - allv.mean()) ** 2 for v in values)
    ss_within = ss_total - ss_between
    df_b, df_w = k - 1, n - k
    ms_w = ss_within / df_w
    if ms_w == 0:
        raise UserError(f'"{outcome}" does not vary within the groups, so an ANOVA can\'t be run.')
    res = stats.f_oneway(*values)
    eta2 = ss_between / ss_total
    omega2 = (ss_between - df_b * ms_w) / (ss_total + ms_w)
    lev = stats.levene(*values, center="mean")
    if lev.pvalue < 0.05:
        warn.append(
            f"The groups' spreads differ (Levene's test {_p(lev.pvalue)}), so the ANOVA may be off; "
            "Kruskal-Wallis does not assume equal spreads."
        )
    for name, v in groups.items():
        _normal_warn(v, f'The values in "{name}"', warn, "Kruskal-Wallis test")
    tukey = stats.tukey_hsd(*values)
    tci = tukey.confidence_interval(0.95)
    pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            pairs.append([names[j], names[i], tukey.statistic[j, i], tci.low[j, i], tci.high[j, i], tukey.pvalue[j, i]])
    desc_rows = []
    for name, v in groups.items():
        m, lo, hi = _mean_ci(v)
        desc_rows.append([name, len(v), m, v.std(ddof=1), lo, hi])
    tables = [
        _table("Descriptives", ["Group", "N", "Mean", "SD", "95% CI low", "95% CI high"], desc_rows),
        _table(
            "One-way ANOVA",
            ["Source", "Sum of squares", "df", "Mean square", "F", "p"],
            [["Between groups", ss_between, df_b, ss_between / df_b, res.statistic, res.pvalue],
             ["Within groups", ss_within, df_w, ms_w, None, None],
             ["Total", ss_total, n - 1, None, None, None]],
        ),
        _table("Effect size", ["Measure", "Value"], [["Eta squared (η²)", eta2], ["Omega squared (ω²)", omega2]]),
        _table(
            "Tukey HSD comparisons",
            ["Group", "Compared with", "Mean difference", "95% CI low", "95% CI high", "p"],
            pairs,
            note="Mean difference is the first group minus the second; p is adjusted for multiple comparisons.",
        ),
    ]
    stat = f"F({df_b}, {df_w}) = {_f(res.statistic)}, {_p(res.pvalue)}, η² = {_nz(eta2)}, ω² = {_nz(omega2)}"
    if res.pvalue < 0.05:
        sig = [f'"{a}" and "{b}" ({_p(p)})' for a, b, _d, _l, _h, p in pairs if p < 0.05]
        post = (
            f" Tukey's test found differences between {', '.join(sig)}." if sig
            else " Tukey's test found no single pair of groups that differed."
        )
        summary = f'"{outcome}" differed between the groups of "{group}", {stat}.{post}'
    else:
        summary = f'"{outcome}" did not differ significantly between the groups of "{group}", {stat}.'
    charts = [
        _box(f'"{outcome}" by "{group}"', outcome, groups),
        _mean_bars(f'Mean "{outcome}" by "{group}"', outcome, groups),
    ]
    return _result(f'One-way ANOVA: "{outcome}" by "{group}"', summary, tables, charts, warn, n)


def anova_twoway(df, outcome, factor_a, factor_b):
    """The effect of two grouping factors and their interaction (type II sums of squares)."""
    import statsmodels.api as sm
    from statsmodels.formula.api import ols

    warn = []
    if factor_a == factor_b:
        raise UserError("Pick two different factors.")
    frame = _complete(
        pd.DataFrame({"y": _numbers(df, outcome, warn), "a": _labels(df, factor_a), "b": _labels(df, factor_b)}),
        warn,
    )
    la, lb = _levels(frame["a"], factor_a), _levels(frame["b"], factor_b)
    for levels, name in ((la, factor_a), (lb, factor_b)):
        if len(levels) < 2:
            raise UserError(f'"{name}" needs at least two groups, but has {len(levels)}.')
    cells = frame.groupby(["a", "b"])["y"].agg(["count", "mean", "std"])
    if len(cells) < len(la) * len(lb):
        raise UserError(
            f'Every combination of "{factor_a}" and "{factor_b}" needs at least one row; '
            f"{len(la) * len(lb) - len(cells)} of them have none."
        )
    if len(frame) <= len(cells):
        raise UserError("Each combination of the two factors needs at least 2 rows.")
    if (cells["count"] < 2).any():
        warn.append("Some combinations of the two factors have only one row, so the results are fragile.")
    _repeat_warn(df, frame.index, warn)
    model = ols("y ~ C(a) * C(b)", data=frame).fit()
    aov = sm.stats.anova_lm(model, typ=2)
    ss_res = aov.loc["Residual", "sum_sq"]
    labels = {"C(a)": factor_a, "C(b)": factor_b, "C(a):C(b)": f"{factor_a} × {factor_b}", "Residual": "Residual"}
    rows, parts = [], []
    for key, label in labels.items():
        ss, dof, f, p = aov.loc[key, ["sum_sq", "df", "F", "PR(>F)"]]
        pe = ss / (ss + ss_res) if key != "Residual" else None
        rows.append([label, ss, dof, ss / dof, f, p, pe])
        if key != "Residual":
            what = f'interaction of "{factor_a}" and "{factor_b}"' if ":" in key else f'main effect of "{label}"'
            parts.append(
                f"{what}: "
                f"F({_dof(dof)}, {_dof(aov.loc['Residual', 'df'])}) = {_f(f)}, {_p(p)}, partial η² = {_nz(pe)}"
            )
    cell_rows, bar_groups = [], {}
    for (a, b), row in cells.reindex(pd.MultiIndex.from_product([la, lb])).iterrows():
        cell_rows.append([a, b, row["count"], row["mean"], row["std"]])
        bar_groups[f"{a} / {b}"] = frame.loc[(frame["a"] == a) & (frame["b"] == b), "y"].to_numpy(float)
    tables = [
        _table("Cell means", [factor_a, factor_b, "N", "Mean", "SD"], cell_rows),
        _table(
            "Two-way ANOVA",
            ["Source", "Sum of squares", "df", "Mean square", "F", "p", "Partial η²"],
            rows,
            note="Type II sums of squares.",
        ),
    ]
    summary = "Two-way ANOVA on " + f'"{outcome}": ' + "; ".join(parts) + "."
    charts = [_mean_bars(f'Mean "{outcome}" by "{factor_a}" and "{factor_b}"', outcome, bar_groups)]
    return _result(
        f'Two-way ANOVA: "{outcome}" by "{factor_a}" and "{factor_b}"', summary, tables, charts, warn, len(frame)
    )


def kruskal(df, outcome, group):
    """Three or more groups, without assuming normal data."""
    from scipy import stats

    warn = []
    frame, groups = _k_groups(df, outcome, group, warn, "Kruskal-Wallis test")
    values = list(groups.values())
    n, k = len(frame), len(values)
    if np.ptp(frame["y"].to_numpy(float)) == 0:
        raise UserError(f'Every value in "{outcome}" is the same, so there is nothing to test.')
    res = stats.kruskal(*values)
    eps2 = res.statistic / (n - 1)
    ranks = stats.rankdata(np.concatenate(values))
    starts = np.cumsum([0] + [len(v) for v in values])
    rows = [[name, len(v), np.median(v), ranks[starts[i]:starts[i + 1]].mean()] for i, (name, v) in enumerate(groups.items())]
    tables = [
        _table("Descriptives", ["Group", "N", "Median", "Mean rank"], rows),
        _table("Kruskal-Wallis test", ["H", "df", "p", "Epsilon squared (ε²)"], [[res.statistic, k - 1, res.pvalue, eps2]]),
    ]
    stat = f"H({k - 1}) = {_f(res.statistic)}, {_p(res.pvalue)}, ε² = {_nz(eps2)}"
    if res.pvalue < 0.05:
        summary = f'"{outcome}" differed between the groups of "{group}", {stat}.'
    else:
        summary = f'"{outcome}" did not differ significantly between the groups of "{group}", {stat}.'
    charts = [_box(f'"{outcome}" by "{group}"', outcome, groups)]
    return _result(f'Kruskal-Wallis: "{outcome}" by "{group}"', summary, tables, charts, warn, n)


def chi_square(df, rows, cols):
    """Are two categories related? Fisher's exact test for a 2x2 table."""
    from scipy import stats

    warn = []
    frame, table = _crosstab(df, rows, cols, warn)
    for levels, name in ((table.index, rows), (table.columns, cols)):
        if len(levels) < 2:
            raise UserError(f'"{name}" has only one value here, so there is nothing to compare.')
    n = len(frame)
    _repeat_warn(df, frame.index, warn)
    chi2, p, dof, expected = stats.chi2_contingency(table.to_numpy(), correction=False)
    v = math.sqrt(chi2 / (n * (min(table.shape) - 1)))
    tests = [["Pearson chi-square", chi2, dof, p]]
    is_2x2 = table.shape == (2, 2)
    if is_2x2:
        odds, fisher_p = stats.fisher_exact(table.to_numpy())
        tests.append(["Fisher's exact test", None, None, fisher_p])
    else:
        low = (expected < 5).mean()
        if low > 0.2 or expected.min() < 1:
            warn.append(
                f"{(expected < 5).sum()} of {expected.size} cells {'expects' if (expected < 5).sum() == 1 else 'expect'} fewer than 5 rows, so the "
                "chi-square p-value may be off. Combining small categories would help."
            )
    effects = [["Cramér's V", v]] + ([["Odds ratio", odds]] if is_2x2 else [])
    tables = [
        _count_table(f'Counts: "{rows}" by "{cols}"', table, rows, cols),
        _table(
            "Expected counts",
            [f"{rows} / {cols}"] + [str(c) for c in table.columns],
            [[k] + list(r) for k, r in zip(table.index, expected)],
        ),
        _table("Tests", ["Test", "Value", "df", "p"], tests,
               note="Fisher's exact test is used for a 2x2 table." if is_2x2 else None),
        _table("Effect size", ["Measure", "Value"], effects),
    ]
    chi = f"χ²({dof}, N = {n}) = {_f(chi2)}"
    if is_2x2:
        related = "were related" if fisher_p < 0.05 else "were not significantly related"
        odds_text = f", odds ratio = {_f(odds)}" if np.isfinite(odds) and odds > 0 else ""
        summary = f'"{rows}" and "{cols}" {related}, Fisher\'s exact test {_p(fisher_p)}{odds_text}; {chi}, V = {_nz(v)}.'
    else:
        related = "were related" if p < 0.05 else "were not significantly related"
        summary = f'"{rows}" and "{cols}" {related}, {chi}, {_p(p)}, V = {_nz(v)}.'
    charts = []
    if table.size <= MAX_GROUPS:
        charts.append({
            "kind": "bar",
            "title": f'Counts: "{rows}" by "{cols}"',
            "yLabel": "Count",
            "bars": [{"name": f"{a} / {b}", "value": int(table.loc[a, b])} for a in table.index for b in table.columns],
        })
    return _result(f'Chi-square test: "{rows}" by "{cols}"', summary, tables, charts, warn, n)


def correlation(df, columns, method="pearson"):
    """How strongly numeric columns move together (Pearson, Spearman or Kendall)."""
    from scipy import stats

    tests = {"pearson": (stats.pearsonr, "r"), "spearman": (stats.spearmanr, "rs"), "kendall": (stats.kendalltau, "τ")}
    if method not in tests:
        raise UserError('The method must be "pearson", "spearman" or "kendall".')
    func, sym = tests[method]
    warn = []
    columns = list(dict.fromkeys(_list(columns)))
    if len(columns) < 2:
        raise UserError("Pick at least two columns to correlate.")
    frame = _complete(pd.DataFrame({c: _numbers(df, c, warn) for c in columns}), warn)
    n = len(frame)
    if n < 3:
        raise UserError("Correlation needs at least 3 rows with a number in every chosen column.")
    for c in columns:
        if np.ptp(frame[c]) == 0:
            raise UserError(f'Every value in "{c}" is the same, so it can\'t be correlated.')
    r = pd.DataFrame(1.0, index=columns, columns=columns)
    p = pd.DataFrame(np.nan, index=columns, columns=columns)
    pairs = []
    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            res = func(frame[a], frame[b])
            r.loc[a, b] = r.loc[b, a] = res.statistic
            p.loc[a, b] = p.loc[b, a] = res.pvalue
            lo = hi = None
            if method == "pearson":
                ci = res.confidence_interval()
                lo, hi = ci.low, ci.high
            pairs.append([a, b, res.statistic, lo, hi, res.pvalue, n])
    label = {"pearson": "Pearson", "spearman": "Spearman", "kendall": "Kendall's tau"}[method]
    tables = [
        _table(f"{label} correlations ({sym})", [""] + columns, [[c] + list(r.loc[c]) for c in columns], note=f"n = {n} for every pair."),
        _table("p-values", [""] + columns, [[c] + list(p.loc[c]) for c in columns]),
        _table("Pairs", ["Column 1", "Column 2", sym, "95% CI low", "95% CI high", "p", "n"], pairs),
    ]

    def stat(rv, pv):
        dof = "" if method == "kendall" else f"({n - 2})"
        return f"{sym}{dof} = {_nz(rv)}, {_p(pv)}"

    if len(columns) == 2:
        a, b, rv, _lo, _hi, pv, _n = pairs[0]
        if pv < 0.05:
            summary = f'"{a}" and "{b}" were {_strength(rv)} {"positively" if rv > 0 else "negatively"} correlated, {stat(rv, pv)}.'
        else:
            summary = f'"{a}" and "{b}" were not significantly correlated, {stat(rv, pv)}.'
        x, y = frame[a].to_numpy(float), frame[b].to_numpy(float)
        charts = [_scatter(f'"{b}" against "{a}"', a, b, x, y, np.polyfit(x, y, 1))]
    else:
        sig = [row for row in pairs if row[5] < 0.05]
        a, b, rv, _lo, _hi, pv, _n = max(pairs, key=lambda row: abs(row[2]))
        summary = (
            f"{len(sig)} of {len(pairs)} pairs were significantly correlated (p < .05). "
            f'The strongest was "{a}" and "{b}", {stat(rv, pv)}.'
        )
        charts = []
    return _result(f"{label} correlation", summary, tables, charts, warn, n)


def _design(df, outcome, predictors, warn):
    """The predictors as model columns: numbers as they are, categories as 0/1 columns."""
    predictors = list(dict.fromkeys(_list(predictors)))
    if not predictors:
        raise UserError("Pick at least one predictor.")
    if outcome in predictors:
        raise UserError(f'"{outcome}" can\'t be both the outcome and a predictor.')
    raw, categorical = {}, []
    for c in predictors:
        s = _col(df, c)
        if _kind(s, _present(s)) == "numeric":
            raw[c] = _numbers(df, c, warn)
        else:
            raw[c] = _labels(df, c)
            categorical.append(c)
    return pd.DataFrame(raw), predictors, categorical


def _dummies(frame, predictors, categorical, notes):
    cols = {"(Intercept)": np.ones(len(frame))}
    for c in predictors:
        if c not in categorical:
            cols[c] = frame[c].to_numpy(float)
            continue
        levels = _levels(frame[c], c)
        if len(levels) < 2:
            raise UserError(f'"{c}" has only one value here, so it can\'t be a predictor.')
        notes.append(f'"{c}" is compared with "{levels[0]}".')
        for level in levels[1:]:
            cols[f"{c}: {level}"] = (frame[c] == level).to_numpy(float)
    X = pd.DataFrame(cols, index=frame.index)
    if len(X) <= X.shape[1]:
        raise UserError(f"There are too few rows ({len(X)}) for this many predictors.")
    if np.linalg.matrix_rank(X.to_numpy()) < X.shape[1]:
        raise UserError(
            "Some predictors carry the same information (one is a copy or a mix of others). "
            "Remove one and try again."
        )
    return X


def linear_regression(df, outcome, predictors):
    """Predict a numeric outcome from one or more columns (ordinary least squares)."""
    import statsmodels.api as sm

    warn = []
    y = _numbers(df, outcome, warn)
    raw, predictors, categorical = _design(df, outcome, predictors, warn)
    raw["__y"] = y
    frame = _complete(raw, warn)
    for c in predictors:
        _id_warn(df, c, frame.index, warn, "a predictor")
    notes = []
    X = _dummies(frame, predictors, categorical, notes)
    yv = frame["__y"].to_numpy(float)
    model = sm.OLS(yv, X).fit()
    ci = model.conf_int()
    coef_rows = [
        [term, model.params[term], model.bse[term], model.tvalues[term], model.pvalues[term], ci.loc[term, 0], ci.loc[term, 1]]
        for term in X.columns
    ]
    tables = [
        _table("Coefficients", ["Term", "B", "SE", "t", "p", "95% CI low", "95% CI high"], coef_rows, note=" ".join(notes) or None),
        _table(
            "Model fit",
            ["N", "R²", "Adjusted R²", "F", "df1", "df2", "p"],
            [[len(yv), model.rsquared, model.rsquared_adj, model.fvalue, model.df_model, model.df_resid, model.f_pvalue]],
        ),
    ]
    summary = (
        f'The model explained {100 * model.rsquared:.0f}% of the variance in "{outcome}", '
        f"R² = {_nz(model.rsquared)}, adjusted R² = {_nz(model.rsquared_adj)}, "
        f"F({_dof(model.df_model)}, {_dof(model.df_resid)}) = {_f(model.fvalue)}, {_p(model.f_pvalue)}."
    )
    terms = list(X.columns[1:])
    if len(predictors) == 1 and not categorical:
        t = terms[0]
        summary += (
            f' Each one-unit increase in "{t}" went with a change of {_f(model.params[t])} in "{outcome}" '
            f"(95% CI {_f(ci.loc[t, 0])} to {_f(ci.loc[t, 1])}, {_p(model.pvalues[t])})."
        )
        x = frame[t].to_numpy(float)
        charts = [_scatter(f'"{outcome}" against "{t}"', t, outcome, x, yv, (model.params[t], model.params["(Intercept)"]))]
    else:
        sig = [f'"{t}" (B = {_f(model.params[t])}, {_p(model.pvalues[t])})' for t in terms if model.pvalues[t] < 0.05]
        summary += f" Significant predictors: {', '.join(sig)}." if sig else " No single predictor was significant."
        charts = [_scatter("Predicted against actual", "Predicted", f'Actual "{outcome}"', model.fittedvalues, yv, (1.0, 0.0))]
    return _result(f'Linear regression: "{outcome}"', summary, tables, charts, warn, len(yv))


def logistic_regression(df, outcome, predictors):
    """Predict a yes/no outcome from one or more columns."""
    import warnings

    import statsmodels.api as sm

    warn = []
    labels = _labels(df, outcome)
    raw, predictors, categorical = _design(df, outcome, predictors, warn)
    raw["__y"] = labels
    frame = _complete(raw, warn)
    for c in predictors:
        _id_warn(df, c, frame.index, warn, "a predictor")
    levels = _levels(frame["__y"], outcome, at_most=10**9)
    if len(levels) != 2:
        found = f" ({_named_list(levels)})" if levels else ""
        raise UserError(
            f'Logistic regression needs an outcome with exactly two values, but "{outcome}" has {len(levels)}{found}.'
        )
    event = levels[1]
    y = (frame["__y"] == event).to_numpy(float)
    notes = [f'Models the chance that "{outcome}" is "{event}" rather than "{levels[0]}".']
    X = _dummies(frame, predictors, categorical, notes)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = sm.Logit(y, X).fit(disp=0, maxiter=200)
        except np.linalg.LinAlgError:
            raise UserError("The model could not be fitted. A predictor may split the outcome perfectly.")
    if any(type(w.message).__name__ in ("PerfectSeparationWarning", "ConvergenceWarning", "HessianInversionWarning") for w in caught) or not model.mle_retvals.get("converged", True):
        warn.append(
            "The model did not settle on stable estimates, often because a predictor splits the "
            "outcome (almost) perfectly. Treat the odds ratios with caution."
        )
    ci = model.conf_int()
    rows = [
        [term, model.params[term], model.bse[term], model.tvalues[term], model.pvalues[term],
         np.exp(model.params[term]), np.exp(ci.loc[term, 0]), np.exp(ci.loc[term, 1])]
        for term in X.columns
    ]
    tables = [
        _table("Coefficients", ["Term", "B", "SE", "z", "p", "Odds ratio", "OR 95% CI low", "OR 95% CI high"], rows, note=" ".join(notes)),
        _table(
            "Model fit",
            ["N", f'Rows with "{event}"', "Log-likelihood", "McFadden R²", "Likelihood-ratio χ²", "df", "p"],
            [[len(y), int(y.sum()), model.llf, model.prsquared, model.llr, model.df_model, model.llr_pvalue]],
        ),
    ]
    better = "better than chance" if model.llr_pvalue < 0.05 else "no better than chance"
    summary = (
        f'The model predicted whether "{outcome}" is "{event}" {better}, '
        f"χ²({_dof(model.df_model)}) = {_f(model.llr)}, {_p(model.llr_pvalue)}, McFadden R² = {_nz(model.prsquared)}."
    )
    terms = list(X.columns[1:])
    if len(terms) == 1:
        t = terms[0]
        odds = f"{_f(np.exp(model.params[t]))} (95% CI {_f(np.exp(ci.loc[t, 0]))} to {_f(np.exp(ci.loc[t, 1]))}, {_p(model.pvalues[t])})"
        if categorical:
            c = categorical[0]
            summary += f' The odds for "{t[len(c) + 2:]}" were {odds} times those for "{_levels(frame[c], c)[0]}".'
        else:
            summary += f' Each one-unit increase in "{t}" multiplied the odds by {odds}.'

    bars = [
        {"name": t, "value": float(np.exp(model.params[t])), "low": float(np.exp(ci.loc[t, 0])), "high": float(np.exp(ci.loc[t, 1]))}
        for t in terms
    ]
    charts = [{"kind": "bar", "title": "Odds ratios (with 95% CI)", "yLabel": "Odds ratio", "bars": bars}]
    return _result(f'Logistic regression: "{outcome}"', summary, tables, charts, warn, len(y))


TESTS = {
    f.__name__: f
    for f in (
        describe, frequencies, normality, t_one_sample, t_independent, t_paired, mann_whitney,
        wilcoxon, anova_oneway, anova_twoway, kruskal, chi_square, correlation,
        linear_regression, logistic_regression,
    )
}


def print_result(result):
    """Print a result the way the app shows it."""
    print(result["title"], "\n")
    print(result["summary"])
    for w in result["warnings"]:
        print("Note:", w)
    for t in result["tables"]:
        print("\n" + t["title"])
        print(pd.DataFrame(t["rows"], columns=t["columns"]).to_string(index=False))
        if t.get("note"):
            print(t["note"])


# Engine: called by the browser worker; never copied into saved scripts ---------------------------

SCIPY_FREE = {"describe", "frequencies"}
NEEDS_STATSMODELS = {"anova_twoway", "linear_regression", "logistic_regression"}
_loaded = {}


def packages_for(test=None, file_name=None):
    """The Pyodide packages a test or a file needs, beyond pandas."""
    if file_name is not None:
        return ["openpyxl"] if file_name.lower().endswith((".xlsx", ".xlsm")) else []
    return (
        ["openpyxl"]
        + ([] if test in SCIPY_FREE else ["scipy"])
        + (["statsmodels"] if test in NEEDS_STATSMODELS else [])
    )


def _safe(fn):
    """Turn exceptions into {"error": message} with a message safe to show."""
    import json
    import traceback

    try:
        return fn()
    except UserError as e:
        return json.dumps({"error": str(e)}), None
    except MemoryError:
        return json.dumps({"error": "This is too much data for the browser. Try a smaller file."}), None
    except Exception:
        traceback.print_exc()
        return json.dumps({"error": "Something went wrong with this file or these choices. Check the columns and try again."}), None


def _load_options(text):
    """LoadOptions from the screens, checked against a strict list. header/skip None means "work it out"."""
    import json

    bad = UserError("Those file options are not valid.")
    raw = json.loads(text) if text else {}
    if not isinstance(raw, dict) or set(raw) - {"header", "skip", "decimal", "thousands", "missing", "units"}:
        raise bad

    def small_int(v, top):
        if v is None:
            return None
        if type(v) is not int or not 0 <= v <= top:
            raise bad
        return v

    def by_column(v, check):
        if v is None:
            return {}
        if not isinstance(v, dict) or len(v) > 50:
            raise bad
        for col, x in v.items():
            if not 0 < len(col) <= 300 or not check(x):
                raise bad
        return v

    def code(c):
        if isinstance(c, str):
            return 0 < len(c) <= 20
        return type(c) in (int, float) and abs(c) < 1e12  # also rules out NaN and infinity

    def unit(u):
        return isinstance(u, str) and 0 < len(u) <= 10 and u.isprintable() and not any(ch.isdigit() or ch.isspace() for ch in u)

    opts = {
        "header": small_int(raw.get("header"), 100),
        "skip": small_int(raw.get("skip"), 10),
        "decimal": raw.get("decimal", "."),
        "thousands": raw.get("thousands"),
        "missing": by_column(raw.get("missing"), lambda x: isinstance(x, list) and 0 < len(x) <= 10 and all(map(code, x))),
        "units": by_column(raw.get("units"), unit),
    }
    if opts["decimal"] not in (".", ",") or opts["thousands"] not in (None, ".") or (opts["thousands"] and opts["decimal"] != ","):
        raise bad
    return opts


def _raw_rows(path, sheet):
    """The first rows of the file as text cells, numbered the way read_data's header and skip count them."""
    import itertools

    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in ("xlsx", "xlsm"):
        frame = pd.read_excel(path, sheet_name=sheet, header=None, nrows=50, engine="openpyxl")
        return [["" if pd.isna(v) else str(v) for v in row] for row in frame.itertuples(index=False)], None
    with open(path, "rb") as f:
        text = _decode(f.read())
    sep = "\t" if ext == "tsv" else _sniff(text)
    try:
        return list(itertools.islice(csv.reader(io.StringIO(text), delimiter=sep), 50)), sep
    except csv.Error:
        return [], sep


def _is_number(text):
    try:
        return math.isfinite(float(text.strip().replace(",", ".")))
    except ValueError:
        return False


def _header_row(raw):
    """The row that holds the column names when rows above it look like a title, else None."""
    widths = [sum(1 for c in row if c.strip()) for row in raw]
    if not widths:
        return None
    need = max(2, -(-max(widths) // 2))
    for i, w in enumerate(widths[:20]):
        if w >= need:
            cells = [c for c in raw[i] if c.strip()]
            return i if i + 1 < len(raw) and not any(map(_is_number, cells)) else None
    return None


def _is_qualtrics(raw, header):
    return len(raw) > header + 2 and any(c.lstrip().startswith('{"ImportId"') for c in raw[header + 2])


MISSING_CODES = [-99999, -9999, -999, -99, -9, 77, 88, 99, 777, 888, 999, 7777, 8888, 9999, 99999]
DECIMAL_COMMA = r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d+"
US_THOUSANDS = r"[+-]?\d{1,3}(?:,\d{3})+"
GROUPED = r"[+-]?\d{1,3}(?:\.\d{3})+,\d+"
WHOLE = r"[+-]?\d+"
UNIT = r"[+-]?\d+(?:\.\d+)?\s*([^\s\d.,+-][^\s\d]{0,9})"
DATE = r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?: \d{1,2}:\d{2}(?::\d{2})?)?"


def _far_codes(nums):
    """Missing-value codes (999, -99 and the like) that sit far outside a column's other values."""
    codes = [c for c in MISSING_CODES if (nums == c).any()]
    others = nums[~nums.isin(codes)]
    if not codes or len(others) < 5:
        return []
    lo, hi = others.min(), others.max()
    spread = max(hi - lo, 1)
    return [
        (c, int((nums == c).sum()), lo, hi) for c in codes
        if (c < 0 <= lo) or c - hi > spread or lo - c > spread
    ]


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _issues(df, raw, sep, opts, auto_header, text_file):
    """Problems in a freshly read file, each with the LoadOptions that fix (or undo) it."""
    import json

    issues = []
    base = {k: v for k, v in opts.items() if v not in (None, ".", {}) or k in ("header", "skip")}

    def fix(**change):
        out = {**base, **change}
        return {k: v for k, v in out.items() if v not in (None, {}) and not (k == "decimal" and v == ".")}

    def add(id_, message, action=None, fix_=None, applied=False):
        issue = {"id": id_, "message": message}
        if fix_ is not None:
            try:  # never offer a fix that _load_options would refuse (very long names, odd units)
                _load_options(json.dumps(fix_))
            except UserError:
                fix_, applied = None, False
        if fix_ is not None:
            issue.update(fix=fix_, action=action or "Undo")
        if applied:
            issue["applied"] = True
        issues.append(issue)

    header, skip = opts["header"], opts["skip"]
    if header and auto_header:
        add("header", f"Row {header + 1} is used as the column names, because the rows above it look like a title.", applied=True)
    elif header:
        add("header", f"Row {header + 1} is used as the column names; the rows above it are left out.",
            fix_={k: v for k, v in fix(header=0, skip=None).items() if k not in ("missing", "units")}, applied=True)
    else:
        row = _header_row(raw)
        if row:
            add("header", f"Row {row + 1} looks like the column names, and the rows above it like a title.",
                f"Use row {row + 1} as the headers", {k: v for k, v in fix(header=row, skip=None).items() if k not in ("missing", "units")})
    qualtrics = _is_qualtrics(raw, header)
    if skip:
        what = "This is a Qualtrics export, so the 2 rows under the column names (question text and import codes) were left out." if qualtrics and skip == 2 else f"The {_plural(skip, 'row', 'rows')} under the column names are left out."
        add("skip", what, fix_=fix(skip=0), applied=True)
    elif qualtrics:
        add("skip", "This looks like a Qualtrics export: the 2 rows under the column names hold question text and import codes, not answers.",
            "Leave out those 2 rows", fix(skip=2))
    if any(i["id"] == "header" and not i.get("applied") for i in issues):
        return issues  # the columns change once the headers are right

    floats = any(pd.api.types.is_float_dtype(df[c]) and (df[c].dropna() % 1 != 0).any() for c in df.columns)
    comma, grouped, dates = [], False, []
    for c in df.columns:
        s = df[c]
        present = _present(s)
        if not len(present):
            continue
        kind = _kind(s, present)
        if pd.api.types.is_datetime64_any_dtype(s):
            dates.append(c)
            continue
        if kind == "numeric":
            nums = pd.to_numeric(present, errors="coerce")
            if not pd.api.types.is_numeric_dtype(s):
                odd = present[nums.isna()]
                if len(odd):
                    examples = _named_list(list(dict.fromkeys(odd.tolist()))[:3])
                    add(f"text:{c}",
                        f'"{c}" is mostly numbers, but {_plural(len(odd), "value is not", "values are not")} ({examples}). '
                        f'{"It is" if len(odd) == 1 else "They are"} treated as missing.')
            for code, count, lo, hi in _far_codes(nums.dropna()):
                add(f"missing:{c}:{code:g}",
                    f'"{c}" has {code:g} in {_plural(count, "row", "rows")}, far from its other values ({lo:g} to {hi:g}). '
                    "It may be a code for a missing answer.",
                    f"Treat {code:g} as missing", fix(missing={**opts["missing"], c: [*opts["missing"].get(c, []), code]}))
            continue
        if bool(pd.api.types.is_bool_dtype(s)) or pd.api.types.is_numeric_dtype(s):
            continue
        is_comma = present.str.fullmatch(DECIMAL_COMMA)
        # "1,234" or "12,500" alone are more likely US thousands than decimals: don't call those a decimal comma.
        if is_comma.any() and not present[is_comma].str.fullmatch(US_THOUSANDS).all() and (is_comma | present.str.fullmatch(WHOLE)).mean() >= 0.8:
            comma.append(c)
            grouped = grouped or present.str.fullmatch(GROUPED).any()
            continue
        unit = present.str.extract(f"^{UNIT}$", expand=False)
        if len(present) >= 3 and unit.notna().all() and unit.nunique() == 1:
            u = unit.iloc[0]
            add(f"units:{c}", f'"{c}" has a unit after every number (like "{present.iloc[0]}"), so it is read as text.',
                f'Remove "{u}" and read as numbers', fix(units={**opts["units"], c: u}))
            continue
        if present.str.fullmatch(DATE).mean() >= 0.8:
            dates.append(c)

    if comma:
        where = f"{_named_list(comma)} {'uses' if len(comma) == 1 else 'use'} a decimal comma (like \"{_present(df[comma[0]]).iloc[0]}\")"
        if not text_file:
            add("decimal", f"{where}, stored as text. Fix it in Excel, or save the sheet as CSV and open that.")
        elif sep == "," or floats:
            add("decimal", f"{where}, so {'it is' if len(comma) == 1 else 'they are'} read as text.")
        else:
            add("decimal", f"{where}, so {'it is' if len(comma) == 1 else 'they are'} read as text, not numbers.",
                "Read 3,5 as 3.5", fix(decimal=",", thousands="." if grouped else None))
    elif opts["decimal"] == ",":
        also = " and 1.234,5 as 1234.5" if opts["thousands"] else ""
        add("decimal", f"Numbers with a decimal comma are read as numbers (3,5 as 3.5{also}).",
            fix_=fix(decimal=None, thousands=None), applied=True)
    for c, codes in opts["missing"].items():
        for code in codes:
            shown = code if isinstance(code, str) else f"{code:g}"
            rest = {**opts["missing"], c: [x for x in codes if x != code]}
            add(f"missing:{c}:{shown}", f'{shown} in "{c}" is treated as missing.',
                fix_=fix(missing={k: v for k, v in rest.items() if v}), applied=True)
    for c, u in opts["units"].items():
        add(f"units:{c}", f'"{u}" is removed from "{c}", so it is read as numbers.',
            fix_=fix(units={k: v for k, v in opts["units"].items() if k != c}), applied=True)
    if dates:
        look = "looks like dates" if len(dates) == 1 else "look like dates"
        add("dates", f"{_named_list(dates)} {look}. Dates are read as text here, so they can't be used as numbers.")
    said = _repeated(df, df.index)
    if said:
        add("repeats", f"{said} Tests that compare groups assume each row is a different person.")
    if raw and len(raw) > header:
        names = [c.strip() for c in raw[header] if c.strip()]
        twice = [n for n in dict.fromkeys(names) if names.count(n) > 1]
        if twice:
            add("duplicates", f"More than one column is called {_named_list(twice)}, so the copies have .1, .2 added to their names.")
    if len(df) < 3:
        add("rows", f"The file has only {_plural(len(df), 'row', 'rows')} of data, too few for most tests.")
    return issues


def engine_load(path, name, sheet=None, options=None):
    """Read the file at `path` (named `name` by the person) and describe it as a DataShape.

    `options` is LoadOptions as JSON. The last good file stays loaded if this one fails."""
    import json

    def load():
        opts = _load_options(options)
        sheets, chosen = [], None
        if name.lower().endswith((".xlsx", ".xlsm")):
            import openpyxl

            try:
                sheets = openpyxl.load_workbook(path, read_only=True).sheetnames
            except Exception:
                raise UserError("This workbook could not be opened. Check it is an Excel .xlsx file.")
            chosen = sheet or (sheets[0] if sheets else None)
            if chosen not in sheets:
                raise UserError(f'The workbook has no sheet called "{chosen}".')
        raw, sep = _raw_rows(path, chosen)
        auto_header = opts["header"] is None
        if auto_header:
            # A title line above the headers in a text file breaks the table (or shifts it), so skip it.
            row = _header_row(raw) if sep else None
            opts["header"] = row if row and all(len(raw[i]) < len(raw[row]) for i in range(row)) else 0
        if opts["skip"] is None:
            opts["skip"] = 2 if _is_qualtrics(raw, opts["header"]) else 0
        df = read_data(path, sheet=chosen, **opts)
        issues = _issues(df, raw, sep, opts, auto_header, sep is not None)
        _loaded.clear()
        _loaded.update(df=df, path=path, name=name, sheet=chosen, options=opts)
        shape_ = {"fileName": name, "sheets": sheets, "sheet": chosen, **shape(df), "issues": issues}
        return json.dumps(_clean(shape_), allow_nan=False), None

    return _safe(load)


def engine_run(test, params_json):
    """Run a test on the loaded file. Returns (result JSON, xlsx bytes)."""
    import inspect
    import json
    import warnings

    def run():
        if "df" not in _loaded:
            raise UserError("Open a file first.")
        fn = TESTS.get(test)
        if fn is None:
            raise UserError("That test is not available.")
        names = list(inspect.signature(fn).parameters)[1:]
        params = {k: v for k, v in json.loads(params_json).items() if k in names and v not in (None, "", [])}
        missing = [k for k in names if k not in params and inspect.signature(fn).parameters[k].default is inspect.Parameter.empty]
        if missing:
            raise UserError("Fill in every choice for this test first.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = fn(_loaded["df"], **params)
        result = _clean({"test": test, **result})
        result["code"] = make_code(test, params, result["title"])
        return json.dumps(result, allow_nan=False), make_xlsx(result)

    return _safe(run)


def _clean(obj):
    """Make a result JSON-safe: plain numbers, NaN as null."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    return str(obj)


def _comment(text):
    """Text from the file for a one-line comment: ascii() escapes line breaks and every non-ASCII letter."""
    return ascii(str(text))[1:-1]


def make_code(test, params, title):
    """A standalone script that reproduces this result from the original file."""
    import ast

    tree = ast.parse(SOURCE)  # noqa: F821 (set by the worker before this file runs)
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            defs[node.targets[0].id] = node
    keep, stack = set(), [test, "read_data", "print_result"]
    while stack:
        name = stack.pop()
        if name in keep or name not in defs:
            continue
        keep.add(name)
        stack.extend(n.id for n in ast.walk(defs[name]) if isinstance(n, ast.Name) and n.id in defs)
    imports = [ast.get_source_segment(SOURCE, n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]  # noqa: F821
    body = [ast.get_source_segment(SOURCE, n) for n in tree.body if getattr(n, "name", None) in keep or (isinstance(n, ast.Assign) and n.targets[0].id in keep)]  # noqa: F821
    name, sheet = _loaded["name"], _loaded["sheet"]
    pip = ["pandas"] + ([] if test in SCIPY_FREE else ["scipy"]) + (["statsmodels"] if test in NEEDS_STATSMODELS else [])
    if sheet is not None:
        pip.append("openpyxl")
    # File, sheet and column names come from a shared file, so they go in through ascii() and the script stays
    # pure ASCII: a name can't change how Python decodes the script (a "coding:" comment once let one escape).
    args = "".join(f", {k}={v!a}" for k, v in params.items())
    read = f"read_data({name!a}" + (f", sheet={sheet!a}" if sheet is not None else "")
    opts = _loaded["options"]
    for key, default in (("header", 0), ("skip", 0), ("decimal", "."), ("thousands", None), ("missing", {}), ("units", {})):
        if opts[key] != default:
            read += f", {key}={opts[key]!a}"  # values only; the keys are this fixed list
    read += ")"
    header = "\n".join([
        "# -*- coding: utf-8 -*-",
        f"# {_comment(title)}",
        f"# Reproduces a result made in labbenchos from {_comment(name)}.",
        f"# Needs Python 3.10 or newer: pip install {' '.join(pip)}",
        "# Put this script in the same folder as the data file, then run it with python.",
    ])
    # Windows consoles and pipes default to cp1252, which can't print letters like the minus sign in headers.
    main = (
        f'if __name__ == "__main__":\n    import sys\n\n    if hasattr(sys.stdout, "reconfigure"):  # IDLE and notebooks have no reconfigure\n'
        f'        sys.stdout.reconfigure(encoding="utf-8")\n'
        f"    df = {read}\n    print_result({test}(df{args}))\n"
    )
    code = "\n\n\n".join([header + "\n\n" + "\n".join(imports), *body, main])
    # The copied functions have a few non-ASCII letters, all in plain strings and comments: escape them too.
    return code.encode("ascii", "backslashreplace").decode("ascii")


def make_xlsx(result):
    """The result as a workbook: a Summary sheet, then one sheet per table."""
    import datetime
    import re

    from openpyxl import Workbook
    from openpyxl.styles import Font

    def put(ws, row):
        ws.append(row)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"  # text from the data, never a formula

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    file_name = _loaded["name"] + (f" (sheet {_loaded['sheet']})" if _loaded.get("sheet") else "")
    for label, value in [
        ("Title", result["title"]),
        ("Summary", result["summary"]),
        ("Warnings", "\n".join(result["warnings"]) or "None"),
        ("Rows used (n)", result["n"]),
        ("File", file_name),
        ("Date", datetime.date.today().isoformat()),
    ]:
        put(ws, [label, value])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 100
    used = {"summary"}
    for t in result["tables"]:
        title = re.sub(r"[\[\]:*?/\\\']", " ", t["title"]).strip()[:31] or "Table"
        base, i = title, 2
        while title.lower() in used:
            title = f"{base[:27]} ({i})"
            i += 1
        used.add(title.lower())
        sheet = wb.create_sheet(title)
        put(sheet, [t["title"]])
        sheet.cell(1, 1).font = Font(bold=True)
        put(sheet, t["columns"])
        for cell in sheet[2]:
            cell.font = Font(bold=True)
        for row in t["rows"]:
            put(sheet, row)
        if t.get("note"):
            put(sheet, [])
            put(sheet, [t["note"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
