import datetime

import pytest

from documents import form_reader as fr

ETHICS = """Certificate of Approval
Title of Study: Sleep and attention in adults
Approval Number: Pro00151738
Research Ethics Board 1
Date of Approval: March 5, 2025
Expiry Date: 2026-03-04
"""
FUNDING = """Funding Agency:
Example Council
Program: Insight Grant
Award Number: 435-2024-0123
Amount awarded: $45,000.00
Start Date: 1 April 2025
End Date: 31 March 2028
"""


def test_reads_an_ethics_form():
    assert fr.read_text(ETHICS, "ethics")["fields"] == {
        "approval_number": "Pro00151738",
        "title": "Sleep and attention in adults",
        "approval_date": "2025-03-05",
        "expiry_date": "2026-03-04",
        "board": "Research Ethics Board",
    }


def test_reads_a_funding_form_and_defaults_the_currency():
    assert fr.read_text(FUNDING, "funding")["fields"] == {
        "funder": "Example Council",
        "program": "Insight Grant",
        "award_number": "435-2024-0123",
        "amount": "45000.00",
        "currency": "CAD",
        "start_date": "2025-04-01",
        "end_date": "2028-03-31",
    }


def test_a_stated_currency_wins():
    assert fr.read_text("Amount awarded: 12,500 USD", "funding")["fields"] == {
        "amount": "12500.00",
        "currency": "USD",
    }


def test_a_field_it_is_unsure_of_is_left_out():
    text = "Approval Number:\nExpiry Date: 03/04/2026\nApproval Date: 15/04/2026"
    assert fr.read_text(text, "ethics")["fields"] == {"approval_date": "2026-04-15"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2025-03-05", datetime.date(2025, 3, 5)),
        ("5th March 2025", datetime.date(2025, 3, 5)),
        ("Sept 9, 2025", datetime.date(2025, 9, 9)),
        ("31/12/2025", datetime.date(2025, 12, 31)),
        ("03/04/2025", None),
        ("2025-02-31", None),
        ("soon", None),
    ],
)
def test_dates(text, expected):
    assert fr.parse_date(text) == expected


def test_what_a_form_says_is_data_and_is_cut_to_length():
    assert "title" not in fr.read_text("Title of Study: " + "x" * 900, "ethics")["fields"]
    long = "x" * 350
    fields = fr.read_text(f"Title of Study: {long}", "ethics")["fields"]
    assert len(fields["title"]) == 300


def test_only_a_pdf_or_text_file_is_read():
    with pytest.raises(ValueError):
        fr.read_form(b"PK\x03\x04", "form.docx", "ethics")
    assert fr.read_form(ETHICS.encode(), "form.txt", "ethics")["fields"]["approval_number"]
