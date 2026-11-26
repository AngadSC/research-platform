"""Demo data for the sample registry and a -80 °C freezer (fake, glycobiology flavour)."""

import datetime

from django.utils import timezone

from samples import services as svc


def seed(lab, users: dict) -> None:
    people = list(users.values())
    pi = users.get("pi") or people[0]
    student = users.get("student") or people[-1]
    lead = users.get("lead") or pi

    def add(kind, name, owner, **fields):
        return svc.create_sample(
            lab=lab, user=pi, data={"kind": kind, "name": name, "owner": owner.pk, **fields}
        )

    cst = add(
        "plasmid",
        "pCW-MalE-CST06 (FAKE)",
        lead,
        description="MBP-tagged sialyltransferase CST-06 for E. coli expression. Fake entry.",
        backbone="pCW",
        insert="CST-06 sialyltransferase",
        resistance="Ampicillin",
        tag="MBP (MalE), His6",
        status="verified",
    )
    pmst = add(
        "plasmid",
        "pMAL-c5X-PmST1-M144D (FAKE)",
        student,
        description="PmST1 M144D mutant, reduced sialidase activity. Fake entry.",
        backbone="pMAL-c5X",
        insert="PmST1 M144D",
        resistance="Ampicillin",
        tag="MBP",
    )
    strains = [
        add(
            "strain",
            f"SHuffle T7 Express + {p.name.split(' ')[0]} (FAKE)",
            p.owner,
            species="Escherichia coli",
            genotype="SHuffle T7 Express (lysY), carrying the plasmid",
            resistance="Ampicillin, spectinomycin",
            parents=[p.pk],
        )
        for p in (cst, pmst)
    ]
    add("primer", "CST06-fwd (FAKE)", lead, sequence="ATGAAGCTGCTGGTTAACGGC")
    add("primer", "CST06-rev (FAKE)", lead, sequence="TTAGCCGTTAACCAGCAGCTTC")
    add("primer", "PmST1-M144D-mut (FAKE)", student, sequence="GGTTTTGATGACTTCGGTCAG")
    batches = [
        add(
            "protein",
            f"MBP-CST06 batch {n} (FAKE)",
            lead,
            concentration=conc,
            buffer="20 mM Tris pH 7.5, 150 mM NaCl, 10% glycerol",
            made_on=timezone.localdate() - datetime.timedelta(days=days),
            parents=[strains[0].pk],
        )
        for n, conc, days in ((1, "2.4 mg/mL", 40), (2, "3.1 mg/mL", 9))
    ]
    add(
        "protein",
        "PmST1-M144D batch 1 (FAKE)",
        student,
        concentration="1.8 mg/mL",
        buffer="20 mM Tris pH 8.0, 100 mM NaCl",
        made_on=timezone.localdate() - datetime.timedelta(days=21),
        parents=[strains[1].pk],
    )

    freezer = svc.create_unit(
        lab=lab,
        user=pi,
        data={
            "name": "-80 °C freezer (FAKE)",
            "kind": "freezer",
            "temperature": "-80 °C",
            "location": "Room 2-14, by the window",
        },
    )
    plasmids, stocks = (
        svc.create_box(
            lab=lab,
            user=pi,
            data={"unit": freezer.pk, "name": name, "rows": 9, "cols": 9, "shelf": shelf},
        )
        for name, shelf in (("Plasmids box 1", "Shelf 1"), ("Glycerol stocks", "Shelf 2"))
    )
    placed = [
        (plasmids, 1, 1, cst, "miniprep", "50 µL", lead),
        (plasmids, 1, 2, cst, "miniprep", "50 µL", lead),
        (plasmids, 1, 3, pmst, "miniprep", "40 µL", student),
        (stocks, 1, 1, strains[0], "glycerol", "1 mL", lead),
        (stocks, 1, 2, strains[1], "glycerol", "1 mL", student),
        (stocks, 2, 1, batches[0], "aliquot", "100 µL", lead),
        (stocks, 2, 2, batches[1], "aliquot", "100 µL", lead),
    ]
    for box, row, col, sample, label, amount, owner in placed:
        svc.place_tube(
            lab=lab,
            user=pi,
            data={
                "box": box.pk,
                "row": row,
                "col": col,
                "sample": sample.pk,
                "label": label,
                "amount": amount,
                "owner": owner.pk,
                "stored_on": timezone.localdate(),
            },
        )
