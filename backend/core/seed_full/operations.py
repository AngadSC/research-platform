"""Lab operations for the full fake lab: ethics, training, onboarding, inventory, calendar,
subjects, institution links, invites and the AI policy. Uses the service layer, acting as the PI,
the lab manager or a project lead. Nothing here calls an outside service, and no address is real
(.test is never mailed: core.email drops reserved TLDs)."""

import datetime
import random
import uuid
from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ethics import services as ethics
from labs import admin_services as admin
from labs import protocols, subjects
from labs import services as lab_services
from labs.models import (
    AiPolicy,
    InventoryUsage,
    OnboardingKind,
    OrderStatus,
)
from training import services as training
from training.models import AppliesTo, TrainingCategory

D = Decimal


def seed(ctx):
    rng = random.Random(11)
    ctx.rng = rng
    seed_lab(ctx)
    seed_ethics(ctx)
    seed_training(ctx)
    seed_onboarding(ctx)
    seed_inventory(ctx, rng)
    seed_calendar(ctx, rng)
    seed_subjects(ctx, rng)
    seed_invites(ctx)


def seed_lab(ctx):
    from core.institution_starters import UALBERTA

    pi = ctx.people["pi"]
    admin.update_lab_details(
        lab=ctx.lab,
        user=pi,
        data={
            "institution_name": UALBERTA,  # also adds the starter links (D149)
            "department": "Department of Psychology (FAKE)",
            "description": "A fake 20-person neuroscience lab used to try the app.",
            "contact_email": "lab@example.test",
        },
    )
    ctx.lab.ai_policy = AiPolicy.FULL  # no AI keys are created anywhere in the seed
    ctx.lab.save(update_fields=["ai_policy", "updated_at"])


# ------------------------------------------------------------------ ethics


def seed_ethics(ctx):
    pi, today, day = ctx.people["pi"], ctx.today, ctx.day
    P = ctx.projects
    # (number, board, title, projects, approved ago, expires in (days), status)
    rows = [
        (
            "REB-2025-0101",
            "University REB (FAKE)",
            "Overnight EEG in adults",
            ["sleep"],
            200,
            165,
            "active",
        ),
        (
            "REB-2025-0145",
            "University REB (FAKE)",
            "Task fMRI of attention",
            ["fmri"],
            300,
            65,
            "active",
        ),
        (
            "ACC-2025-0033",
            "Animal Care Committee (FAKE)",
            "Hippocampal recording in mice",
            ["mouse"],
            345,
            20,
            "active",
        ),
        (
            "REB-2024-0310",
            "University REB (FAKE)",
            "Ageing cohort, wave 3",
            ["ageing", "grant"],
            400,
            330,
            "active",
        ),
        (
            "REB-2023-0077",
            "University REB (FAKE)",
            "Visual crowding psychophysics",
            ["crowding"],
            900,
            -40,
            "expired",
        ),
        (
            "REB-2026-0012",
            "University REB (FAKE)",
            "Resting-state EEG pilot",
            ["eeg"],
            None,
            None,
            "pending",
        ),
        (
            "REB-2022-0200",
            "University REB (FAKE)",
            "Pupillometry pilot",
            ["pupil"],
            1200,
            -150,
            "withdrawn",
        ),
    ]
    made = {}
    for number, board, title, keys, ago, left, status in rows:
        made[number] = ethics.create_approval(
            lab=ctx.lab,
            user=pi,
            data={
                "approval_number": number,
                "board": board,
                "title": f"{title} (FAKE)",
                "projects": [P[k].pk for k in keys],
                "approval_date": today - ago * day if ago else None,
                "expiry_date": today + left * day if left is not None else None,
                "status": status,
                "restricted": number == "REB-2024-0310",  # participant study: leads and PIs only
            },
        )
    # The animal approval expires in 20 days, so a renewal is already with the committee.
    ethics.create_approval(
        lab=ctx.lab,
        user=pi,
        data={"renews": made["ACC-2025-0033"].pk, "approval_number": "ACC-2026-0033"},
    )


# ------------------------------------------------------------------ training


def seed_training(ctx):
    pi, manager = ctx.people["pi"], ctx.people["manager"]
    P, today, day, rng = ctx.projects, ctx.today, ctx.day, ctx.rng
    # (name, category, months valid, applies to, roles, projects)
    reqs = [
        ("TCPS 2: CORE (FAKE)", "ethics", None, AppliesTo.ALL, [], []),
        ("WHMIS (FAKE)", "safety", 12, AppliesTo.ROLES, ["pi", "lab_admin", "member"], []),
        ("Animal care and use (FAKE)", "biosafety", 24, AppliesTo.PROJECTS, [], ["mouse"]),
        ("MRI safety screening (FAKE)", "safety", 12, AppliesTo.PROJECTS, [], ["fmri", "ageing"]),
        ("Research data privacy (FAKE)", "data_privacy", 24, AppliesTo.ALL, [], []),
        ("First aid and CPR (FAKE)", "other", 36, AppliesTo.ROLES, ["pi", "lab_admin"], []),
    ]
    made = []
    for name, category, months, applies, roles, keys in reqs:
        made.append(
            training.create_requirement(
                lab=ctx.lab,
                user=pi,
                data={
                    "name": name,
                    "category": TrainingCategory(category),
                    "validity_months": months,
                    "applies_to": applies,
                    "roles": roles,
                    "projects": [P[k].pk for k in keys],
                    "notes": "Fake requirement.",
                    "url": "https://training.example.invalid/course",
                },
            )
        )
    result = training.compliance(ctx.lab, today=today)
    newest = {"liam", "kai"}
    keys_by_pk = {p.pk: k for k, p in ctx.people.items()}
    for row in result["members"]:
        who = keys_by_pk[row["user"].pk]
        for req in made:
            if row["cells"][str(req.pk)] is None:
                continue
            roll = rng.random()
            if who in newest and roll < 0.7:
                continue  # missing
            if who == "eli" and req.validity_months:
                kind = "expiring"
            elif roll < 0.12:
                continue  # missing
            elif roll < 0.30 and req.validity_months:
                kind = "expiring"
            elif roll < 0.42 and req.validity_months:
                kind = "expired"
            elif roll < 0.56:
                kind = "unverified"
            else:
                kind = "current"
            months = req.validity_months
            if kind == "expiring":
                done = today + rng.randint(5, 55) * day - months * 30 * day
            elif kind == "expired":
                done = today - rng.randint(10, 120) * day - months * 30 * day
            else:
                done = today - rng.randint(20, 330 if months is None else months * 30 - 70) * day
            rec = training.create_record(
                lab=ctx.lab,
                actor=manager,
                data={
                    "user": row["user"],
                    "requirement": req.pk,
                    "completed_on": done,
                    "notes": "Fake record.",
                },
            )
            if kind != "unverified":
                training.verify_record(rec, actor=pi)


# ------------------------------------------------------------------ onboarding


def seed_onboarding(ctx):
    manager = ctx.people["manager"]
    reqs = {r.name: r for r in training_requirements(ctx)}
    new_member = [
        ("Read the lab handbook (FAKE)", "https://handbook.example.invalid", None),
        ("Get a key card and building access (FAKE)", "", None),
        ("Finish TCPS 2: CORE (FAKE)", "", "TCPS 2: CORE (FAKE)"),
        ("Finish WHMIS (FAKE)", "", "WHMIS (FAKE)"),
        ("Set up the lab chat and calendar (FAKE)", "", None),
        ("Meet the lab manager for a safety walk-through (FAKE)", "", None),
        ("Book a first one-on-one with the PI (FAKE)", "", None),
    ]
    departing = [
        ("Hand over data and notebooks (FAKE)", ""),
        ("Return keys and equipment (FAKE)", ""),
        ("Write a handover note for your projects (FAKE)", ""),
    ]
    items = []
    for i, (title, url, training_name) in enumerate(new_member):
        items.append(
            admin.create_onboarding_item(
                lab=ctx.lab,
                user=manager,
                data={
                    "kind": OnboardingKind.NEW_MEMBER,
                    "title": title,
                    "url": url,
                    "order": i,
                    "required": i != 4,
                    "training_requirement": reqs[training_name].pk if training_name else None,
                },
            )
        )
    for i, (title, url) in enumerate(departing):
        admin.create_onboarding_item(
            lab=ctx.lab,
            user=manager,
            data={"kind": OnboardingKind.DEPARTING, "title": title, "url": url, "order": i},
        )
    # How many of the first items each person has done (the newest are mostly not started).
    done = {"liam": 2, "kai": 1, "ben": 4, "ella": 5, "ravi": 6, "zoe": 7, "grace": 7, "mateo": 7}
    for key, user in ctx.people.items():
        if key in ("pi", "manager"):
            continue
        for item in items[: done.get(key, len(items))]:
            admin.set_completion(item, member=user, done=True, by=manager)


def training_requirements(ctx):
    from training.models import TrainingRequirement

    return TrainingRequirement.objects.for_lab(ctx.lab)


# ------------------------------------------------------------------ inventory

# (name, category, location, quantity, unit, low-stock level, owner key)
ITEMS = [
    ("Fetal bovine serum (FAKE)", "reagent", "Freezer B2", 6, "bottle", 3, "manager"),
    ("Phosphate-buffered saline (FAKE)", "reagent", "Cold room shelf 1", 40, "L", 10, "manager"),
    ("Paraformaldehyde 4% (FAKE)", "reagent", "Fume hood cabinet", 2, "L", 2, "hana"),
    ("Isoflurane (FAKE)", "reagent", "Surgery room", 250, "mL", 100, "hana"),
    ("Ethanol 70% (FAKE)", "reagent", "Prep room", 12, "L", 4, "manager"),
    ("Dental cement powder (FAKE)", "reagent", "Surgery room", 3, "tub", 1, "hana"),
    ("Cresyl violet stain (FAKE)", "reagent", "Histology shelf", 500, "mL", 200, "liam"),
    ("DAPI mounting medium (FAKE)", "reagent", "Freezer A1", 8, "vial", 4, "liam"),
    ("Saline 0.9% (FAKE)", "reagent", "Surgery room", 6, "L", 2, "hana"),
    ("Electrode gel (FAKE)", "reagent", "EEG suite", 14, "tube", 5, "priya"),
    ("Pipette tips 200 uL (FAKE)", "consumable", "Bench supply", 12, "box", 6, "manager"),
    ("Pipette tips 10 uL (FAKE)", "consumable", "Bench supply", 4, "box", 6, "manager"),
    ("Microcentrifuge tubes 1.5 mL (FAKE)", "consumable", "Bench supply", 20, "bag", 5, "manager"),
    ("Nitrile gloves, medium (FAKE)", "consumable", "Entry cabinet", 18, "box", 8, "manager"),
    ("Nitrile gloves, small (FAKE)", "consumable", "Entry cabinet", 3, "box", 8, "manager"),
    ("Disposable EEG caps (FAKE)", "consumable", "EEG suite", 30, "each", 10, "priya"),
    ("Abrasive skin prep pads (FAKE)", "consumable", "EEG suite", 200, "each", 60, "priya"),
    ("Surgical sutures (FAKE)", "consumable", "Surgery room", 24, "pack", 8, "hana"),
    ("Cotton swabs (FAKE)", "consumable", "Surgery room", 9, "box", 3, "hana"),
    ("Parafilm roll (FAKE)", "consumable", "Bench supply", 5, "roll", 2, "manager"),
    ("Mouse chow, standard (FAKE)", "consumable", "Animal facility store", 5, "bag", 4, "hana"),
    ("Mouse bedding (FAKE)", "consumable", "Animal facility store", 14, "bag", 6, "hana"),
    ("Nestlets (FAKE)", "consumable", "Animal facility store", 40, "each", 15, "hana"),
    ("Water bottles, spare (FAKE)", "consumable", "Animal facility store", 30, "each", 10, "hana"),
    ("Silicon probe, 64 channel (FAKE)", "equipment", "Rig room", 3, "each", 2, "hana"),
    ("Two-photon microscope (FAKE)", "equipment", "Imaging room", 1, "each", None, "hana"),
    ("Stereotaxic frame (FAKE)", "equipment", "Surgery room", 2, "each", None, "hana"),
    ("Microcentrifuge (FAKE)", "equipment", "Bench 3", 2, "each", None, "manager"),
    ("-80 C freezer (FAKE)", "equipment", "Freezer room", 2, "each", None, "manager"),
    ("64-channel EEG amplifier (FAKE)", "equipment", "EEG suite", 2, "each", None, "priya"),
    ("Eye tracker (FAKE)", "equipment", "Testing room 2", 1, "each", None, "noah"),
    ("Testing laptops (FAKE)", "equipment", "Testing room 1", 6, "each", None, "manager"),
    ("Pupil camera (FAKE)", "equipment", "Storage", 1, "each", None, "eli"),
    ("MATLAB licence (FAKE)", "software_licence", "Department server", 8, "seat", None, "tomas"),
    (
        "Presentation stimulus software (FAKE)",
        "software_licence",
        "Testing room 1",
        4,
        "seat",
        None,
        "noah",
    ),
    (
        "Statistics package licence (FAKE)",
        "software_licence",
        "Department server",
        12,
        "seat",
        None,
        "aisha",
    ),
    ("Lab coats (FAKE)", "other", "Entry cabinet", 22, "each", 8, "manager"),
    ("Safety glasses (FAKE)", "other", "Entry cabinet", 7, "each", 10, "manager"),
    ("Cryo labels (FAKE)", "other", "Bench supply", 6, "roll", 3, "manager"),
    ("Spill kit (FAKE)", "other", "Hallway", 2, "kit", 1, "manager"),
    ("First aid kit (FAKE)", "other", "Hallway", 3, "kit", 1, "manager"),
]
# which items need a calibration or maintenance date, in days from today
DUE = {
    "Two-photon microscope (FAKE)": 12,
    "Microcentrifuge (FAKE)": -20,
    "-80 C freezer (FAKE)": 75,
}

# (item, vendor, catalog, quantity, unit, status)
ORDERS = [
    ("Pipette tips 10 uL (FAKE)", "Example Scientific (FAKE)", "EX-PT10", 10, "box", "requested"),
    (
        "Nitrile gloves, small (FAKE)",
        "Example Scientific (FAKE)",
        "EX-GL-S",
        10,
        "box",
        "requested",
    ),
    ("Safety glasses (FAKE)", "Example Safety (FAKE)", "SG-200", 12, "each", "requested"),
    ("Paraformaldehyde 4% (FAKE)", "Example Chemicals (FAKE)", "PFA-4-1L", 4, "L", "ordered"),
    ("Mouse chow, standard (FAKE)", "Example Animal Supply (FAKE)", "CH-20", 8, "bag", "ordered"),
    ("Fetal bovine serum (FAKE)", "Example Biologics (FAKE)", "FBS-500", 6, "bottle", "ordered"),
    ("Mouse bedding (FAKE)", "Example Animal Supply (FAKE)", "BD-10", 10, "bag", "received"),
    ("Disposable EEG caps (FAKE)", "Example Neuro (FAKE)", "EEG-CAP-64", 20, "each", "received"),
    ("Ethanol 70% (FAKE)", "Example Chemicals (FAKE)", "ETOH-70-4", 8, "L", "received"),
    ("Silicon probe, 64 channel (FAKE)", "Example Neuro (FAKE)", "SP-64", 2, "each", "cancelled"),
    (None, "Example Neuro (FAKE)", "EEG-GEL-X", 12, "tube", "requested"),  # not in stock yet
]

# (protocol, project, notes, [(item, amount, unit)])
PROTOCOLS = [
    (
        "Transcardial perfusion (FAKE)",
        "mouse",
        "Fake protocol. Perfuse with saline, then fix.",
        [
            ("Saline 0.9% (FAKE)", "200", "mL"),
            ("Paraformaldehyde 4% (FAKE)", "150", "mL"),
            ("Isoflurane (FAKE)", "5", "mL"),
        ],
    ),
    (
        "Cresyl violet staining (FAKE)",
        "mouse",
        "Fake protocol for stained sections.",
        [("Cresyl violet stain (FAKE)", "50", "mL"), ("Ethanol 70% (FAKE)", "200", "mL")],
    ),
    (
        "EEG cap fitting (FAKE)",
        "sleep",
        "Fake protocol for a night session.",
        [
            ("Disposable EEG caps (FAKE)", "1", "each"),
            ("Electrode gel (FAKE)", "1", "tube"),
            ("Abrasive skin prep pads (FAKE)", "6", "each"),
        ],
    ),
]


def seed_inventory(ctx, rng):
    manager, today, day = ctx.people["manager"], ctx.today, ctx.day
    items = {}
    for name, cat, place, qty, unit, low, owner in ITEMS:
        items[name] = admin.create_inventory_item(
            lab=ctx.lab,
            user=manager,
            data={
                "name": name,
                "category": cat,
                "location": place,
                "quantity": D(qty),
                "unit": unit,
                "low_stock_at": None if low is None else D(low),
                "owner": ctx.people[owner].pk,
                "serial_number": f"SN-{rng.randint(10000, 99999)}" if cat == "equipment" else "",
                "purchase_date": today - rng.randint(60, 900) * day if cat == "equipment" else None,
                "due_date": today + DUE[name] * day if name in DUE else None,
                "notes": "Fake item.",
            },
        )
    requesters = ["manager", "hana", "priya", "liam", "zoe"]
    for i, (name, vendor, catalog, qty, unit, status) in enumerate(ORDERS):
        order = admin.create_inventory_order(
            lab=ctx.lab,
            user=ctx.people[requesters[i % len(requesters)]],
            data={
                "item": items[name].pk if name else None,
                "name": name or "EEG electrode gel, 250 mL (FAKE)",
                "vendor": vendor,
                "catalog_number": catalog,
                "url": f"https://vendor.example.invalid/{catalog.lower()}",
                "quantity": D(qty),
                "unit": unit,
                "status": OrderStatus.REQUESTED,
                "notes": "Fake order.",
            },
        )
        if status != "requested":
            admin.update_inventory_order(order, user=manager, data={"status": OrderStatus(status)})
    # protocols (the lead writes them) and what people took, with undone mistakes
    for name, key, notes, lines in PROTOCOLS:
        project = ctx.projects[key]
        lead = ctx.people[{"mouse": "hana", "sleep": "priya"}[key]]
        protocol = protocols.create_protocol(
            project=project,
            user=lead,
            data={
                "name": name,
                "notes": notes,
                "reagents": [{"item": items[i].pk, "amount": D(a), "unit": u} for i, a, u in lines],
            },
        )
        for reagent in protocol.reagents.all():
            for _ in range(rng.randint(1, 3)):
                try:
                    protocols.record_use(
                        protocol=protocol,
                        reagent_id=reagent.pk,
                        amount=None,
                        request_id=uuid.UUID(int=rng.getrandbits(128), version=4),
                        user=lead,
                    )
                except ValidationError:  # a fake use the service refuses is skipped
                    pass
    for name, amount, unit, who in [
        ("Nitrile gloves, medium (FAKE)", "1", "box", "zoe"),
        ("Pipette tips 200 uL (FAKE)", "2", "box", "liam"),
        ("Phosphate-buffered saline (FAKE)", "500", "mL", "noah"),
        ("Mouse bedding (FAKE)", "2", "bag", "hana"),
        ("Parafilm roll (FAKE)", "1", "roll", "ella"),
    ]:
        protocols.log_use(
            item=items[name],
            amount=D(amount),
            unit=unit,
            request_id=uuid.UUID(int=rng.getrandbits(128), version=4),
            user=ctx.people[who],
            note="Fake use.",
        )
    # one mistake, undone
    usage = InventoryUsage.objects.for_lab(ctx.lab).filter(reversed_at__isnull=True).first()
    if usage is not None:
        protocols.reverse_use(usage, user=usage.used_by)


# ------------------------------------------------------------------ calendar


def at(ctx, days, hour, minutes=60):
    start = timezone.make_aware(
        datetime.datetime.combine(ctx.today + days * ctx.day, datetime.time(hour))
    )
    return start, start + datetime.timedelta(minutes=minutes)


def seed_calendar(ctx, rng):
    people = ctx.people
    everyone = [u.pk for u in people.values()]
    students = [
        people[k].pk
        for k in (
            "priya",
            "tomas",
            "hana",
            "eli",
            "aisha",
            "noah",
            "sofia",
            "liam",
            "grace",
            "mateo",
        )
    ]
    monday = -ctx.today.weekday()  # offset to this week's Monday
    made = []

    def meet(who, title, days, hour, minutes, attendees, notes="", link=True):
        start, end = at(ctx, days, hour, minutes)
        m = admin.create_meeting(
            lab=ctx.lab,
            user=people[who],
            data={
                "title": f"{title} (FAKE)",
                "starts_at": start,
                "ends_at": end,
                "join_url": "https://meet.example.invalid/room" if link else "",
                "notes": notes,
                "attendees": attendees,
            },
        )
        made.append(m)
        return m

    for week in range(-6, 7):  # the series: six weeks back, six ahead
        meet(
            "pi",
            "Weekly lab meeting",
            monday + 7 * week + 0,
            10,
            60,
            everyone,
            "Fake agenda: updates, blockers, announcements.",
        )
        meet(
            "priya",
            "Journal club",
            monday + 7 * week + 3,
            15,
            60,
            students + [people["ella"].pk],
            "Fake paper of the week.",
        )
    for week in (-4, -2, 0, 2, 4):  # fortnightly
        meet("pi", "Data club", monday + 7 * week + 2, 14, 60, students[:6])
    ones = ["priya", "tomas", "hana", "eli", "aisha", "noah", "sofia", "liam"]
    for i, who in enumerate(ones):
        for week in (-3, 0, 3):
            meet(
                "pi",
                f"One-on-one with {who.title()}",
                monday + 7 * week + i % 5,
                11 + i % 4,
                30,
                [people[who].pk],
            )
    for i, (rig, who) in enumerate(
        [
            ("Two-photon rig", "hana"),
            ("EEG suite", "aisha"),
            ("Testing room 2 (eye tracker)", "noah"),
            ("Surgery room", "liam"),
            ("EEG suite", "grace"),
            ("Two-photon rig", "zoe"),
        ]
    ):
        for n in range(8):  # eight bookings each, spread over past and next six weeks
            meet(
                who,
                f"Booking: {rig}",
                -42 + rng.randint(0, 83),
                9 + (i + n) % 8,
                120,
                [people[who].pk],
                link=False,
            )
    # a few answers to the invitations
    for m in made[:6]:
        for pk in rng.sample(
            list(m.attendees.values_list("pk", flat=True)), k=min(4, m.attendees.count())
        ):
            user = next(u for u in people.values() if u.pk == pk)
            admin.respond_to_meeting(
                m, user=user, status=rng.choice(["accepted", "accepted", "maybe", "declined"])
            )
    for title, days, length, who in [
        ("Lab retreat", 28, 2, "manager"),
        ("Grant deadline", 40, None, "pi"),
        ("Ethics renewal due at the committee", 18, None, "coordinator"),
        ("Conference abstract deadline", 12, None, "tomas"),
        ("Building power shutdown, rigs off", 6, 1, "manager"),
        ("Winter break, lab closed", 35, 10, "pi"),
        ("Thesis defence: Eli Brooks", 50, None, "pi"),
        ("Fire drill", -9, None, "manager"),
        ("Society conference", -30, 4, "priya"),
        ("Lab social", -16, None, "coordinator"),
    ]:
        date = ctx.today + days * ctx.day
        admin.create_lab_event(
            lab=ctx.lab,
            user=people[who],
            data={
                "title": f"{title} (FAKE)",
                "date": date,
                "end_date": date + length * ctx.day if length else None,
                "notes": "Fake event.",
            },
        )


# ------------------------------------------------------------------ subjects


def seed_subjects(ctx, rng):
    project, lead = ctx.projects["mouse"], ctx.people["hana"]
    today, day = ctx.today, ctx.day
    lines = [
        ("C57BL/6J", "Wild type", "Example Mouse Vendor (FAKE)"),
        ("Thy1-GCaMP6s", "Thy1-GCaMP6s +/-", "Example Mouse Vendor (FAKE)"),
        ("PV-Cre", "PV-Cre +/-", "In-house colony (FAKE)"),
    ]
    statuses = ["active"] * 16 + ["stored"] * 3 + ["finished"] * 8 + ["gone"] * 3
    for n, state in enumerate(statuses, start=1):
        line, genotype, source = lines[n % 3]
        subjects.create_subject(
            project=project,
            user=lead,
            data={
                "kind": "animal",
                "code": f"M-{n:03d}",
                "species": "Mus musculus",
                "line": line,
                "genotype": genotype,
                "sex": rng.choice(["female", "male"]),
                "count": 1,
                "source": source,
                "start_date": today - rng.randint(40, 300) * day,
                "location": f"Rack {1 + n % 4}, cage {10 + n}",
                "status": state,
                "approval": "ACC-2025-0033",
                "notes": "Fake mouse." if state != "gone" else "Fake record; culled at endpoint.",
            },
        )


# ------------------------------------------------------------------ invites


def seed_invites(ctx):
    for email, role in [
        ("new.postdoc@example.test", "member"),
        ("visiting.student@example.test", "viewer"),
        ("new.assistant@example.test", "member"),
    ]:
        lab_services.create_invite(lab=ctx.lab, by=ctx.people["pi"], email=email, role=role)
