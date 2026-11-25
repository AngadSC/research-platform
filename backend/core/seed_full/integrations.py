"""Fake connections for the full-size lab: an account or two per provider, links in every state,
the Google Chat bridge, Google Calendar sync rows, a few video meetings and webhooks.

Rows are written directly, with NO tokens and `.invalid` hosts, so nothing here contacts a real
service (same as seed_pilot's seed_drive). Plain tables, then loops.
"""

# ruff: noqa: E501 (the tables below are one row per line)
import datetime
import hashlib

from core.seed_full.people import PROJECTS
from integrations import crypto, registry
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink, Webhook, WebhookKind
from integrations.services import retired_id
from labs.models import (
    ChatSource,
    GoogleCalendarSync,
    GoogleChatBridge,
    LabChatMessage,
    Meeting,
    SyncedEvent,
    VideoProvider,
)

# fmt: off
A, E, R, X = "active", "expired", "revoked", "error"  # X: our side misconfigured

# (person, provider, status). The person key is a key of people.PEOPLE.
ACCOUNTS = [
    # Drive: most of the lab. Coordinator and Liam need to reconnect, Ravi disconnected.
    *[
        (p, "google_drive", A)
        for p in "pi manager priya tomas hana eli aisha noah sofia grace mateo zoe ella owen".split()
    ],
    ("coordinator", "google_drive", E),
    ("liam", "google_drive", E),
    ("ravi", "google_drive", R),
    # Calendar and Meet ride on the same Google sign-in as Drive (D262)
    ("pi", "google_calendar", A),
    ("manager", "google_calendar", A),
    ("priya", "google_calendar", A),
    ("coordinator", "google_calendar", E),
    ("pi", "zoom", A),
    ("manager", "zoom", A),
    ("coordinator", "zoom", R),
    ("manager", "google_chat", A),
    ("pi", "google_chat", A),
    ("priya", "google_chat", E),
    # analysts
    *[(p, "github", A) for p in "priya tomas hana noah sofia mateo eli".split()],
    ("ravi", "github", E),
    ("tomas", "gitlab", A),
    ("noah", "gitlab", A),
    ("sofia", "gitlab", E),
    ("manager", "onedrive", A),
    ("coordinator", "onedrive", A),
    ("liam", "onedrive", X),
    ("ben", "dropbox", A),
    ("zoe", "dropbox", A),
    ("ella", "dropbox", E),
    ("manager", "box", A),
    ("aisha", "box", A),
    ("ravi", "box", A),
    # the ageing cohort's data capture
    ("aisha", "redcap", A),
    ("coordinator", "redcap", A),
    ("priya", "redcap", A),
    ("ravi", "redcap", E),
    ("aisha", "qualtrics", A),
    ("coordinator", "qualtrics", A),
    ("grace", "qualtrics", R),
    ("hana", "protocols_io", A),
    ("liam", "protocols_io", A),
    ("zoe", "protocols_io", E),
    # students keep references
    *[(p, "zotero", A) for p in "eli aisha noah grace mateo ella ben sofia priya".split()],
    ("liam", "zotero", E),
    ("priya", "osf", A),
    ("sofia", "osf", A),
    ("eli", "osf", A),
    ("coordinator", "todoist", A),
    ("zoe", "todoist", A),
    ("ben", "todoist", A),
    ("manager", "trello", A),
    ("noah", "trello", A),
    ("manager", "monday", A),
    ("pi", "monday", A),
]

# Self-hosted providers: the person's own server (fake, never resolves).
INSTANCES = {
    "gitlab": "https://git.northfield.example.invalid",
    "redcap": "https://redcap.northfield.example.invalid",
    # Qualtrics only accepts a qualtrics.com address (instance_host_pattern), so this one host
    # is not .invalid: a made-up tenant that does not exist, and no token is stored anyway.
    "qualtrics": "https://northfield-fake-lab.qualtrics.com",
}

SHA = "0123456789abcdef0123456789abcdef01234567"
SHA2 = "fedcba9876543210fedcba9876543210fedcba98"

# (project, provider, target kind, linker, state, external id, title). State: ok = up to date,
# changed = the remote moved on since it was linked, gone = no longer available. A linker whose
# account is expired or revoked gives a link the daily job cannot check.
LINKS = [
    ("sleep", "google_drive", "project", "priya", "ok", "fakedrive-sleep-protocol", "Sleep protocol v3 (FAKE).docx"),
    ("sleep", "google_drive", "dataset", "aisha", "changed", "fakedrive-eeg-export", "EEG export, night 1 to 20 (FAKE).csv"),
    ("sleep", "google_drive", "document", "zoe", "ok", "fakedrive-sleep-diary", "Sleep diary template (FAKE).xlsx"),
    ("sleep", "zotero", "manuscript", "grace", "ok", "u1:FAKESL22", "Spindles and recall, review (FAKE)"),
    ("sleep", "github", "analysis", "priya", "ok", "example-lab-fake/sleep-eeg-pipeline", "example-lab-fake/sleep-eeg-pipeline (FAKE)"),
    ("sleep", "overleaf", "manuscript", "priya", "ok", "a1b2c3d4e5f60718293a4b01", "Sleep and memory manuscript source (FAKE)"),
    ("sleep", "dropbox", "project", "ella", "gone", "id:FAKEDBX0001", "Thesis figures (FAKE)"),
    ("sleep", "zenodo", "dataset", "aisha", "ok", "9000000001", "Sleep EEG, archived copy (FAKE)"),
    ("fmri", "github", "analysis", "tomas", "changed", f"example-lab-fake/fmri-attention@{SHA}", "fmri-attention at a commit (FAKE)"),
    ("fmri", "gitlab", "result", "tomas", "ok", "fmri-lab/preproc-pipeline", "fmri-lab/preproc-pipeline (FAKE)"),
    ("fmri", "google_drive", "result", "noah", "ok", "fakedrive-fmri-fig2", "Figure 2 draft (FAKE).pdf"),
    ("fmri", "zotero", "decision", "noah", "ok", "u2:FAKEFM22", "Smoothing kernel choice, source (FAKE)"),
    ("fmri", "box", "dataset", "ravi", "changed", "1000000001", "Scanner QA exports (FAKE)"),
    ("fmri", "figshare", "result", "tomas", "ok", "9100000001", "Attention maps, public copy (FAKE)"),
    ("mouse", "protocols_io", "analysis", "hana", "ok", "fake-probe-implant-protocol", "Probe implant protocol (FAKE)"),
    ("mouse", "github", "analysis", "hana", "ok", "example-lab-fake/spike-sorting", "example-lab-fake/spike-sorting (FAKE)"),
    ("mouse", "protocols_io", "document", "liam", "ok", "fake-perfusion-protocol", "Perfusion protocol (FAKE)"),
    ("mouse", "onedrive", "dataset", "liam", "gone", "FAKEONE1.FAKEONE1-1", "Raw probe recordings index (FAKE)"),
    ("mouse", "dropbox", "project", "ben", "ok", "id:FAKEDBX0002", "Animal weights (FAKE)"),
    ("mouse", "google_drive", "dataset", "zoe", "changed", "fakedrive-mouse-log", "Surgery log (FAKE).xlsx"),
    ("mouse", "frdr", "dataset", "hana", "ok", "10.20383/fake.mouse01", "Hippocampal recordings, deposit (FAKE)"),
    ("ageing", "redcap", "dataset", "aisha", "ok", "1000001", "Ageing cohort wave 3 project (FAKE)"),
    ("ageing", "qualtrics", "dataset", "aisha", "changed", "SV_fakeAG0001", "Sleep questionnaire (FAKE)"),
    ("ageing", "redcap", "project", "coordinator", "ok", "1000002", "Ageing cohort scheduling (FAKE)"),
    ("ageing", "qualtrics", "dataset", "coordinator", "gone", "SV_fakeAG0002", "Old consent survey (FAKE)"),
    ("ageing", "redcap", "dataset", "priya", "ok", "1000003", "Actigraphy log project (FAKE)"),
    ("ageing", "redcap", "dataset", "ravi", "ok", "1000004", "Home visit forms (FAKE)"),
    ("ageing", "qualtrics", "dataset", "grace", "ok", "SV_fakeAG0003", "Follow-up survey (FAKE)"),
    ("ageing", "google_drive", "dataset", "aisha", "ok", "fakedrive-ageing-codebook", "Ageing codebook (FAKE).xlsx"),
    ("ageing", "google_drive", "dataset", "ravi", "ok", "fakedrive-ageing-visits", "Visit schedule (FAKE).xlsx"),
    ("ageing", "google_drive", "document", "coordinator", "changed", "fakedrive-ageing-sop", "Recruitment SOP (FAKE).docx"),
    ("ageing", "box", "dataset", "aisha", "ok", "1000000002", "Cognitive battery scores (FAKE)"),
    ("ageing", "zotero", "decision", "aisha", "ok", "u3:FAKEAG22", "Attrition handling, source (FAKE)"),
    ("ageing", "onedrive", "project", "coordinator", "ok", "FAKEONE2.FAKEONE2-1", "Ageing study folder (FAKE)"),
    ("ageing", "borealis", "dataset", "aisha", "ok", "10.5683/FAKE/AGEING01", "Ageing wave 2, deposit (FAKE)"),
    ("eeg", "github", "analysis", "noah", "ok", "example-lab-fake/eeg-biomarkers", "example-lab-fake/eeg-biomarkers (FAKE)"),
    ("eeg", "gitlab", "analysis", "noah", "gone", "eeg-lab/pilot-scripts", "eeg-lab/pilot-scripts (FAKE)"),
    ("eeg", "zotero", "document", "ella", "ok", "u4:FAKEEG22", "Resting-state EEG review (FAKE)"),
    ("eeg", "google_drive", "document", "tomas", "changed", "fakedrive-eeg-plan", "EEG pilot plan (FAKE).docx"),
    ("eeg", "dropbox", "project", "ella", "ok", "id:FAKEDBX0003", "Pilot photos (FAKE)"),
    ("reading", "github", "analysis", "sofia", "ok", "example-lab-fake/reading-trial", "example-lab-fake/reading-trial (FAKE)"),
    ("reading", "gitlab", "analysis", "sofia", "ok", "reading-lab/trial-analysis", "reading-lab/trial-analysis (FAKE)"),
    ("reading", "google_drive", "dataset", "mateo", "ok", "fakedrive-reading-scores", "Reading scores (FAKE).csv"),
    ("reading", "osf", "dataset", "sofia", "gone", "ab3cd", "Reading trial preregistration (FAKE)"),
    ("reading", "zotero", "manuscript", "sofia", "ok", "u5:FAKERD22", "Reading interventions meta-analysis (FAKE)"),
    ("reading", "zotero", "decision", "mateo", "changed", "u6:FAKERD33", "Outcome measure, source (FAKE)"),
    ("grant", "google_drive", "document", "pi", "ok", "fakedrive-grant-draft", "Renewal draft (FAKE).docx"),
    ("grant", "google_drive", "project", "manager", "ok", "fakedrive-grant-budget", "Budget workbook (FAKE).xlsx"),
    ("grant", "box", "document", "manager", "gone", "1000000003", "Old budget (FAKE)"),
    ("grant", "google_drive", "project", "hana", "ok", "fakedrive-grant-figures", "Grant figures (FAKE)"),
    ("grant", "overleaf", "manuscript", "tomas", "ok", "a1b2c3d4e5f60718293a4b02", "Renewal LaTeX source (FAKE)"),
    ("grant", "overleaf", "document", "pi", "ok", "a1b2c3d4e5f60718293a4b03", "Letters of support (FAKE)"),
    ("grant", "zotero", "manuscript", "priya", "ok", "u7:FAKEGR22", "Renewal references (FAKE)"),
    ("crowding", "google_drive", "dataset", "eli", "ok", "fakedrive-crowding-data", "Crowding trials (FAKE).csv"),
    ("crowding", "zotero", "manuscript", "eli", "ok", "u8:FAKECR22", "Crowding review (FAKE)"),
    ("crowding", "github", "analysis", "eli", "changed", f"example-lab-fake/crowding-psychophysics@{SHA2}", "crowding-psychophysics at a commit (FAKE)"),
    ("crowding", "osf", "dataset", "eli", "ok", "cr0wd", "Crowding data, OSF (FAKE)"),
    ("crowding", "zenodo", "result", "sofia", "ok", "9000000002", "Crowding figures, archived (FAKE)"),
    ("crowding", "dropbox", "project", "ben", "changed", "id:FAKEDBX0004", "Stimulus images (FAKE)"),
    ("crowding", "zenodo", "dataset", "eli", "gone", "9000000003", "Crowding raw data (FAKE)"),
    ("crowding", "overleaf", "manuscript", "eli", "ok", "a1b2c3d4e5f60718293a4b04", "Crowding paper source (FAKE)"),
    ("pupil", "google_drive", "dataset", "eli", "gone", "fakedrive-pupil-data", "Pupil traces (FAKE).csv"),
    ("pupil", "protocols_io", "document", "hana", "ok", "fake-pupil-protocol", "Pupillometry protocol (FAKE)"),
    ("pupil", "zotero", "decision", "eli", "ok", "u9:FAKEPU22", "Blink handling, source (FAKE)"),
    ("pupil", "overleaf", "manuscript", "eli", "ok", "a1b2c3d4e5f60718293a4b05", "Pilot write-up source (FAKE)"),
]  # fmt: skip

# Where an item's page lives, as a fake .invalid address.
URL = "https://{provider}.example.invalid/{id}"

# (provider, person who owns the sign-in) -> a Google Chat space. Lab chat first, then a project's.
CHAT_SPACES = [
    (None, "manager", "spaces/FAKELABCHAT01", "Northfield lab chat (FAKE)"),
    ("ageing", "pi", "spaces/FAKEAGEING01", "Ageing cohort team (FAKE)"),
]

# (title, days from today, provider, organiser, attendees). The organiser's own account holds
# the call. Coordinator's Zoom is revoked: that call is left as a plain meeting.
MEETINGS = [
    ("Lab meeting (FAKE)", 2, VideoProvider.ZOOM, "pi", ["manager", "priya", "tomas", "hana", "aisha", "noah"]),
    ("Grant writing session (FAKE)", 3, VideoProvider.GOOGLE_MEET, "manager", ["pi", "priya", "tomas", "hana"]),
    ("Journal club (FAKE)", 5, VideoProvider.GOOGLE_MEET, "priya", ["aisha", "grace", "zoe", "ella"]),
    ("Ageing cohort check-in (FAKE)", 6, VideoProvider.ZOOM, "manager", ["aisha", "coordinator", "ravi"]),
    ("Site visit prep (FAKE)", 8, VideoProvider.ZOOM, "coordinator", ["pi", "manager"]),
    ("Committee meeting, Eli (FAKE)", 12, "", "eli", ["pi", "sofia"]),
]  # fmt: skip

WEBHOOKS = [
    ("Project news to the lab channel (FAKE)", WebhookKind.SLACK, "hooks.slack.example.invalid", ["project.created", "meeting.created"], True, 200),
    ("Data log for the manager (FAKE)", WebhookKind.WEBHOOK, "hooks.example.invalid", ["dataset.created", "analysis.created"], True, 500),
    ("Old Zapier hook (FAKE)", WebhookKind.WEBHOOK, "zapier.example.invalid", ["decision.created"], False, None),
]  # fmt: skip


# fmt: on


def target(ctx, project, kind, user):
    """An item of this kind in the project to hang a link on: the first one there, else a minimal
    one of ours (another seed module may have made them, or not)."""
    model = ExternalLink._meta.get_field(kind).related_model
    found = model.objects.for_lab(ctx.lab).filter(project=project).order_by("created_at").first()
    if found:
        return found
    fake = {
        "dataset": {
            "name": "Link target dataset (FAKE)",
            "version_label": "v1",
            "created_by": user,
        },
        "analysis": {
            "title": "Link target analysis (FAKE)",
            "code_repo_url": "https://github.example.invalid/example-lab-fake/target",
            "code_commit": SHA,
            "ran_by": user,
            "ran_at": ctx.now,
        },
        "manuscript": {
            "title": "Link target manuscript (FAKE)",
            "url": "https://manuscript.example.invalid/x",
            "created_by": user,
        },
        "decision": {
            "title": "Link target decision (FAKE)",
            "decided_on": ctx.today,
            "decided_by": user,
        },
        "document": {
            "title": "Link target document (FAKE)",
            "created_by": user,
            "updated_by": user,
        },
    }
    if kind == "result":
        fake["result"] = {
            "title": "Link target result (FAKE)",
            "analysis": target(ctx, project, "analysis", user),
            "created_by": user,
        }
    return model.objects.create(lab=ctx.lab, project=project, **fake[kind])


def seed(ctx):
    lab, people, now, day = ctx.lab, ctx.people, ctx.now, ctx.day

    # ---- accounts: no tokens, so nothing can reach a real service
    accounts = {}
    for n, (who, provider, status) in enumerate(ACCOUNTS):
        spec = registry.PROVIDERS[provider]
        fake_id = f"fake-{provider}-{who}"
        retired = status == AccountStatus.REVOKED
        row = ConnectedAccount.objects.create(
            lab=lab,
            user=people[who],
            provider=provider,
            external_account_id=retired_id(fake_id) if retired else fake_id,
            external_email="" if retired else people[who].email,
            granted_scopes=[] if retired else list(spec.scopes),
            status=status,
            instance_url=INSTANCES.get(provider, ""),
            connected_at=now - (10 + n * 3) * day,
            last_used_at=None if status != AccountStatus.ACTIVE else now - (n % 6) * day,
        )
        accounts[who, provider] = row

    # ---- links on every project, in every state
    for project_key, provider, kind, who, state, ext_id, title in LINKS:
        spec = registry.PROVIDERS[provider]
        # the linker's own account; none for the providers read without one
        account = accounts.get((who, provider)) if spec.needs_account else None
        linked = now - 20 * day
        link = {
            "lab": lab,
            "project": ctx.projects[project_key],
            "provider": provider,
            "connected_account": account,
            "external_id": ext_id,
            "url": URL.format(provider=provider, id=ext_id.replace("@", "/")),
            "title": title,
            "linked_by": people[who],
            "linked_modified_at": linked,
            "linked_version": "v1",
            "remote_modified_at": linked,
            "remote_version": "v1",
            "last_checked_at": now - 3 * day,
        }
        if state == "changed":
            link |= {"remote_version": "v2", "remote_modified_at": now - 2 * day}
        if state == "gone":
            link["unavailable_since"] = now - 2 * day
        if kind != "project":
            lead = people[PROJECTS[project_key][2]]
            link[kind] = target(ctx, ctx.projects[project_key], kind, lead)
        if provider == "overleaf":  # no API: never checked
            link["last_checked_at"] = None
        ExternalLink.objects.create(**link)

    # ---- Google Chat: the lab chat's link, a project chat's, and what came in from Google
    for project_key, who, space, name in CHAT_SPACES:
        GoogleChatBridge.objects.create(
            lab=lab,
            account=accounts[who, "google_chat"],
            project=ctx.projects[project_key] if project_key else None,
            created_by=people[who],
            space=space,
            space_name=name,
            cursor="2026-01-01T00:00:00Z",
            last_polled_at=now - day / 24,
        )
    for n, text in enumerate(
        ["Who has the key to the scanner room? (FAKE)", "Booked for Thursday (FAKE)", "Thanks!"]
    ):
        LabChatMessage.objects.create(
            lab=lab,
            body=text,
            source=ChatSource.GOOGLE_CHAT,
            external_author="Visitor Example (FAKE)",
            external_id=f"{CHAT_SPACES[0][2]}/messages/FAKEMSG{n:04d}",
            via_account=accounts["manager", "google_chat"],
        )

    # ---- Google Calendar sync: settings per person, and what was pushed
    for who, provider, status in ACCOUNTS:
        if provider != "google_calendar":
            continue
        active = status == AccountStatus.ACTIVE
        sync = GoogleCalendarSync.objects.create(
            lab=lab,
            user=people[who],
            account=accounts[who, provider],
            show_google_events=active,
            push_meetings=who in ("pi", "manager"),
            push_tasks=who == "pi",
            push_deadlines=who == "manager",
            app_calendar_id=f"fakecal-{who}@group.calendar.example.invalid" if active else "",
            last_synced_at=now - day / 4 if active else None,
            last_error="" if active else "Reconnect Google Calendar: Google stopped accepting it.",
        )
        if sync.pushes and active:
            for item in range(3):
                key = f"meeting:fake-{who}-{item}"
                SyncedEvent.objects.create(
                    lab=lab,
                    sync=sync,
                    key=key,
                    event_id=f"fakeevent{who}{item}",
                    fingerprint=hashlib.sha256(key.encode()).hexdigest(),
                )

    # ---- meetings with a video call made by the organiser's own account
    for title, ahead, video, who, others in MEETINGS:
        starts = now.replace(minute=0, second=0, microsecond=0) + ahead * day
        account = accounts.get((who, "zoom" if video == VideoProvider.ZOOM else "google_calendar"))
        meeting = Meeting.objects.create(
            lab=lab,
            title=title,
            starts_at=starts,
            ends_at=starts + datetime.timedelta(hours=1),
            join_url=(
                f"https://{video or 'meet'}.example.invalid/j/fake{ahead:04d}" if video else ""
            ),
            created_by=people[who],
            video_provider=video,
            external_id=f"fake-call-{ahead}" if video else "",
            video_account=account,
        )
        meeting.attendees.set([people[who], *(people[k] for k in others)])

    # ---- webhooks last: the audit events above would otherwise queue deliveries to them
    for name, kind, host, events, active, last in WEBHOOKS:
        Webhook.objects.create(
            lab=lab,
            name=name,
            kind=kind,
            url_ct=crypto.encrypt(f"https://{host}/hooks/fake-path-0001"),
            secret_ct=crypto.encrypt("fake-signing-secret-not-real"),
            host=host,
            events=events,
            is_active=active,
            created_by=people["manager"],
            last_attempt_at=now - day if last else None,
            last_status=last,
        )
