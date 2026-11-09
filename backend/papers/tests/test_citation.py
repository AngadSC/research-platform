"""Exact citation strings: multiple authors, missing fields, escaping."""

from types import SimpleNamespace

from papers.citation import apa, bibtex, chicago, mla, split_name


def paper(**kw):
    defaults = {
        "title": "On computable numbers",
        "authors": [],
        "year": None,
        "venue": "",
        "doi": "",
        "url": "",
    }
    return SimpleNamespace(**{**defaults, **kw})


FULL = paper(
    title="Computing machinery and intelligence",
    authors=["Turing, Alan Mathison", "Hopper, Grace", "Lovelace, Ada"],
    year=1950,
    venue="Mind",
    doi="10.1093/mind/LIX.236.433",
)


def test_apa_three_authors():
    assert apa(FULL) == (
        "Turing, A. M., Hopper, G., & Lovelace, A. (1950). Computing machinery and intelligence. "
        "Mind. https://doi.org/10.1093/mind/LIX.236.433"
    )


def test_apa_no_author_no_year_no_venue_uses_url():
    p = paper(url="https://example.org/x")
    assert apa(p) == "On computable numbers. (n.d.). https://example.org/x"


def test_apa_two_authors_and_title_punctuation():
    p = paper(title="Is it true?", authors=["Ada Lovelace", "Turing, A."], year=2001)
    assert apa(p) == "Lovelace, A., & Turing, A. (2001). Is it true?"


def test_apa_more_than_twenty_authors_uses_ellipsis():
    names = [f"Author{i}, A." for i in range(1, 23)]
    p = paper(authors=names, year=2020, title="Big")
    out = apa(p)
    assert (
        out.startswith("Author1, A., ") and "Author19, A., . . . Author22, A. (2020). Big." in out
    )


def test_mla():
    assert mla(FULL) == (
        'Turing, Alan Mathison, et al. "Computing machinery and intelligence." Mind, 1950, '
        "https://doi.org/10.1093/mind/LIX.236.433."
    )
    two = paper(authors=["Lovelace, Ada", "Alan Turing"], year=1950)
    assert mla(two) == 'Lovelace, Ada, and Alan Turing. "On computable numbers." 1950.'
    assert mla(paper()) == '"On computable numbers."'


def test_chicago():
    assert chicago(FULL) == (
        'Turing, Alan Mathison, Grace Hopper, and Ada Lovelace. "Computing machinery and '
        'intelligence." Mind (1950). https://doi.org/10.1093/mind/LIX.236.433.'
    )
    assert chicago(paper()) == '"On computable numbers." n.d.'
    assert chicago(paper(authors=["Plato,"], venue="Ideas")) == (
        'Plato. "On computable numbers." Ideas (n.d.).'
    )


def test_chicago_more_than_ten_authors_lists_seven():
    names = [f"F{i}, G{i}" for i in range(1, 12)]
    out = chicago(paper(authors=names, year=2000))
    assert out.startswith("F1, G1, G2 F2, G3 F3, G4 F4, G5 F5, G6 F6, G7 F7, et al.")


def test_bibtex():
    assert bibtex(FULL) == (
        "@article{turing1950computing,\n"
        "  author = {Turing, Alan Mathison and Hopper, Grace and Lovelace, Ada},\n"
        "  title = {Computing machinery and intelligence},\n"
        "  journal = {Mind},\n"
        "  year = {1950},\n"
        "  doi = {10.1093/mind/LIX.236.433},\n"
        "}"
    )
    assert bibtex(paper()) == "@misc{computable,\n  title = {On computable numbers},\n}"


def test_bibtex_escapes_and_keeps_organisations_whole():
    p = paper(title="100% of {x} & y", authors=["World Health Organization,"], url="http://x/{a}")
    assert bibtex(p) == (
        "@misc{worldhealthorganizationpaper,\n"
        "  author = {{World Health Organization}},\n"
        r"  title = {100\% of \{x\} \& y},"
        "\n"
        "  url = {http://x/a},\n"
        "}"
    )


def test_split_name():
    assert split_name("Lovelace, Ada") == ("Lovelace", "Ada")
    assert split_name("Ada King Lovelace") == ("Lovelace", "Ada King")
    assert split_name("World Health Organization,") == ("World Health Organization", "")
    assert split_name("Plato") == ("Plato", "")
