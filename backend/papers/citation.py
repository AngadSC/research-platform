"""The one citation formatter: APA 7, MLA 9, Chicago 17 (bibliography) and BibTeX, from a paper's
metadata. Plain text, so the italics those styles want on a journal name are left to the reader.
Titles are used as typed (no case changes, which would mangle gene names and acronyms).

ponytail: a paper has no volume, issue or page fields, so those parts of each style are absent;
add the fields and one line per style if someone needs them."""

import re
import unicodedata


def split_name(author: str) -> tuple[str, str]:
    """(family, given). "Family, Given" as written, "Given Family" otherwise. A trailing comma
    ("World Health Organization,") gives an empty given name: the whole name is the family."""
    author = " ".join(author.split())
    if "," in author:
        family, given = author.split(",", 1)
        return family.strip(), given.strip()
    given, _, family = author.rpartition(" ")
    return family, given


def _end(text: str) -> str:
    """`text` ending in sentence punctuation, without doubling it."""
    return text if text.endswith((".", "?", "!")) else text + "."


def _link(p) -> str:
    return f"https://doi.org/{p.doi}" if p.doi else p.url


def _inverted(author: str) -> str:
    family, given = split_name(author)
    return f"{family}, {given}" if given else family


def _given_first(author: str) -> str:
    family, given = split_name(author)
    return f"{given} {family}" if given else family


def _initials(given: str) -> str:
    """ "Jean-Paul Q." -> "J.-P. Q." (already-initialled "A.M." -> "A. M.")."""
    return " ".join(
        "-".join(f"{part[0].upper()}." for part in word.split("-") if part)
        for word in given.replace(".", " ").split()
    )


def _apa_name(author: str) -> str:
    family, given = split_name(author)
    return f"{family}, {_initials(given)}" if given else family


def apa(p) -> str:
    names = [_apa_name(a) for a in p.authors]
    if len(names) > 20:
        who = ", ".join(names[:19]) + ", . . . " + names[-1]
    elif len(names) > 1:
        who = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        who = "".join(names)
    year = f"({p.year})." if p.year else "(n.d.)."
    title = _end(p.title)
    parts = [_end(who), year, title] if who else [title, year]  # no author: the title leads
    if p.venue:
        parts.append(_end(p.venue))
    if link := _link(p):
        parts.append(link)
    return " ".join(parts)


def _quoted_title(p) -> str:
    return f'"{_end(p.title)}"'


def mla(p) -> str:
    a = p.authors
    if len(a) > 2:
        who = f"{_inverted(a[0])}, et al."
    elif len(a) == 2:
        who = f"{_inverted(a[0])}, and {_end(_given_first(a[1]))}"
    else:
        who = _end(_inverted(a[0])) if a else ""
    tail = ", ".join(x for x in (p.venue, str(p.year or ""), _link(p)) if x)
    return " ".join(x for x in (who, _quoted_title(p), f"{tail}." if tail else "") if x)


def chicago(p) -> str:
    a = p.authors
    if len(a) > 10:
        who = ", ".join([_inverted(a[0]), *map(_given_first, a[1:7])]) + ", et al."
    elif len(a) > 1:
        head = ", ".join([_inverted(a[0]), *map(_given_first, a[1:-1])])
        who = f"{head}, and {_end(_given_first(a[-1]))}"
    else:
        who = _end(_inverted(a[0])) if a else ""
    year = str(p.year) if p.year else "n.d."
    where = f"{p.venue} ({year})." if p.venue else _end(year)
    link = _link(p)
    return " ".join(x for x in (who, _quoted_title(p), where, f"{link}." if link else "") if x)


_TEX = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


def _tex(text: str) -> str:
    return text.translate(_TEX)


def _bib_name(author: str) -> str:
    family, given = split_name(author)
    return f"{_tex(family)}, {_tex(given)}" if given else "{" + _tex(family) + "}"


def _bib_key(p) -> str:
    family = split_name(p.authors[0])[0] if p.authors else ""
    word = next((w for w in re.findall(r"[^\W_]+", p.title) if len(w) > 3), "paper")
    ascii_key = unicodedata.normalize("NFKD", f"{family}{p.year or ''}{word}").encode(
        "ascii", "ignore"
    )
    return re.sub(r"[^a-z0-9]", "", ascii_key.decode().lower()) or "paper"


def bibtex(p) -> str:
    # a DOI or address can hold braces, which would end the field early; they are never TeX
    literal = re.compile(r"[{}\\]")
    fields = (
        ("author", " and ".join(map(_bib_name, p.authors))),
        ("title", _tex(p.title)),
        ("journal", _tex(p.venue)),
        ("year", p.year or ""),
        ("doi", literal.sub("", p.doi)),
        ("url", literal.sub("", p.url)),
    )
    body = "".join(f"  {name} = {{{value}}},\n" for name, value in fields if value)
    return f"@{'article' if p.venue else 'misc'}{{{_bib_key(p)},\n{body}}}"


STYLES = {"apa": apa, "mla": mla, "chicago": chicago, "bibtex": bibtex}


def cite(paper, style: str) -> str:
    return STYLES[style](paper)
