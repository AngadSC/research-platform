# Vision: the whole project in one place

Written 2026-11-11 from the founders' brief. This is the direction for the next runs. The plan at
the end (Run 6) breaks it into tasks. It adds to [SPEC.md](SPEC.md), it does not replace it.

## The goal

A lab member should be able to do a whole day's research work without leaving labbenchos:

- open every document and file for a project in one place, upload new ones, and edit them;
- pick files from their Google Drive (or other storage) and work on them here;
- run analyses (statistics, figures) on those files, and see past analyses;
- ask Claude for help in a panel on the right that stays open while they move around the app, and
  that can read the lab's documents and files and do things for them;
- use MATLAB through Claude if their lab works in MATLAB.

Participant information stays out of all of this. SPEC.md already says the platform does not store
raw participant data; the AI must never see it either (see "Participant data" below).

## What we can and can't do

Checked 2026-11-11. "Checked" means tested or read from the vendor's own docs; "assumed" needs the
spike named in the plan before we build on it.

| We want | Can we? | The limit | What we do instead |
|---|---|---|---|
| Integrations easy to find for everyone | Yes, done | It was only in PIs' Admin menu | Now in every member's main sidebar (D267) |
| Edit Google Docs, Sheets, Slides inside the app | Mostly | We can show Google's own editor inside a panel of our page. Checked: Google's editor page does not forbid being embedded. Assumed: it only works when the person is signed in to Google in the same browser, and Safari and Firefox block the cookies it needs | Chrome and Edge: edit in the panel. Safari and Firefox: an "Open in Google Docs" button that opens a new tab. Spike B1 confirms which browsers work |
| Build our own editor for Google Docs | No (too big) | Google's Docs API only takes edit commands; a full editor on top of it is months of work and would always lag Google | Use Google's editor (above). Our own lab documents keep using our editor (BlockNote) |
| Edit Word and Excel files inside the app | Partly | Microsoft only lets approved partners embed Office for the web | Convert a copy to Google Docs or Sheets in the person's Drive and edit it there. Self-hosting an office server (Collabora or OnlyOffice) is possible, but both are AGPL and need about 2 GB of RAM; decide later |
| See the person's whole Google Drive inside the app | Not cheaply | Today we use Google's `drive.file` permission: we see only files the person picks or that we create. Picking a folder most likely does not give us the files inside it (old forum reports; spike B1 checks). Seeing everything needs Google's "restricted" Drive permission, which means a paid yearly security assessment (CASA) and weeks of review | A "From Drive" picker that can select many files at once, plus files created from the app (we can always see those). Uploading straight to labbenchos also works. Revisit the restricted permission only if picking proves too painful |
| Claude in a side panel inside the app, not a new tab | Yes, as our own Claude | claude.ai refuses to be embedded in other sites (checked: `X-Frame-Options: SAMEORIGIN`), and a web page cannot control the Claude app or the Claude Chrome extension | We already have our own Claude assistant in the app (D187). Today it is a pop-over that covers the page; it becomes a docked panel on the right that stays open while you move around, can be resized or collapsed, and knows which page you are on |
| Use a person's Claude Pro or Max subscription for that panel | No | Subscriptions only work in Anthropic's own apps. Other apps must use an API key, billed per use | Today each person adds their own key. Add a lab key the PI sets once, with a monthly cap, or include AI in our price. Founders decide (question 1) |
| Claude reads all documents and files | Yes | Today Claude can read projects, tasks, our documents, papers and notes, but not the contents of uploaded files or Drive files | New tools to list and read files: PDF, Word, Excel or CSV, text, images, and Google Docs or Sheets that are linked to the project (exported as text or CSV) |
| Keep participant information away from Claude | Yes, with a flag | Software cannot reliably spot participant data on its own | A "Contains participant data" flag on files, folders, datasets and documents. Flagged items are never given to the AI and are left out of AI search. We ask about it on upload and copy it down from folders. A simple scan for obvious identifiers (emails, phone numbers, health numbers) warns but does not decide |
| Run statistics on files and make figures | Yes | Running code that an AI wrote is the main security risk, and our current server is small | Phase C1: Anthropic's code-execution tool (Python runs on Anthropic's servers, only for unflagged files). Phase C2: our own locked-down runner (Python, R and Octave; no internet, time and memory limits, only the chosen files copied in, on a separate server). Each run is saved as an Analysis in lineage, with its code, input versions and outputs, so it can be rerun |
| Claude uses MATLAB on our server | No | MATLAB licences are per person or per campus. MathWorks' official MATLAB MCP server may only be used as a "Personal Automation Server", not a central one. MATLAB Production Server is a separate, expensive product | GNU Octave in our runner runs most plain `.m` scripts and makes figures (toolboxes differ). Real MATLAB runs on the person's own computer: MathWorks' free MATLAB MCP Core Server plus Claude Desktop, with our connector for the lab's files, works today. An in-app bridge to a person's own MATLAB is a later option |

## How the pieces fit

- **Project files** is one list per project: uploads, Drive files linked or picked, and files the app
  made (figures, exported tables). Each row has Preview, Edit (Google editor panel, or our editor for
  our documents) and Ask Claude.
- **The Claude panel** is the same assistant everywhere. It gets the current page as context ("this
  document", "this task", "these files") and uses the same tools as the MCP connector, so whatever
  a person can do in the panel they can also do from the Claude app.
- **Analyses** are lineage records (they already exist). A run from the panel creates one, links
  its input files and dataset versions, and stores its code and outputs.
- **Permissions do not change.** Claude, Drive files and the runner only ever see what the person
  can already see, through `core/permissions.py`, and flagged participant data is excluded on top.

## What goes to Anthropic

Whatever Claude reads (documents, file contents, analysis outputs) is sent to Anthropic's API under
the key's account. Anthropic's commercial terms say API data is not used for training. Participant
data is never sent, because of the flag. Labs should say this in their ethics applications; the
privacy policy will say it too once these features ship.

## Run 6 plan

Sizes: S is days, M is about a week, L is two weeks or more. The model column follows the
orchestrator's rule of thumb (haiku for mechanical work, sonnet for features, opus for security and
AI work).

### Phase A: quick wins (do first)
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| A1 | Integrations link in every member's sidebar; pointer to Claude and ChatGPT setup | S | orchestrator | done |
| A2 | Docked Claude panel: right side, stays open across pages, resizable and collapsible, remembers its state per browser, sends the current page as context; keyboard shortcut; phone keeps the full-screen sheet | M | sonnet / medium | todo |
| A3 | Participant-data flag on files, folders, datasets and documents; asked on upload, copied down from folders; every AI tool, AI search and the MCP server refuse flagged items; tests in the permission matrix | M | opus / high | todo |
| A4 | AI file tools: `list_files`, `read_file` (PDF, Word, Excel or CSV, text, images) with size limits and untrusted-content wrapping; refuses flagged files (needs A3) | M | opus / high | todo |
| A5 | Lab AI key: a PI or lab admin sets one key for the lab, with a monthly spending cap and per-person usage shown; a person's own key still wins | M | sonnet / medium | todo |

### Phase B: Google inside the app
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| B1 | Spike, half a day: embed a private Google Doc's editor in Chrome, Edge, Safari and Firefox; pick a folder with `drive.file` and check whether its files can be read. Write the result into DECISIONS.md | S | sonnet / medium | todo |
| B2 | Project Files page: one list of uploads, Drive files and app-made files; preview; Edit opens the Google editor in a side panel (or a new tab where B1 says it fails); multi-select "From Drive" picker | L | sonnet / high | todo |
| B3 | Word and Excel: "Edit in Google" makes a Google copy in the person's Drive, linked back to the original | M | sonnet / medium | todo |
| B4 | Claude reads linked Google Docs and Sheets (export to text or CSV), same rules as A4 | S | opus / medium | todo |
| B5 | Decision only: apply for Google's restricted Drive permission if B2 picking is not enough (cost and time in the table above) | S | founders | todo |

### Phase C: analysis
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| C1 | Claude runs Python with Anthropic's code-execution tool on chosen, unflagged files; figures and tables are saved back to the project; each run becomes an Analysis in lineage with its code and inputs | L | opus / high | todo |
| C2 | Our own runner on a separate server: Python, R and Octave in locked-down containers (gVisor, no network, CPU, memory and time limits); same UI as C1; security review before launch | L | opus / high | todo |
| C3 | Analyses page: list runs per project, open outputs, rerun on a newer dataset version, download the code | M | sonnet / medium | todo |

### Phase D: MATLAB
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| D1 | Help page: use your own MATLAB with Claude Desktop (MathWorks' MATLAB MCP Core Server) together with the labbenchos connector | S | haiku / low | todo |
| D2 | Octave in the C2 runner for `.m` scripts | S | sonnet / medium | todo |
| D3 | Optional, only if labs ask: a small helper app that links a person's own MATLAB to the in-app Claude panel | L | opus / high | todo |

Order: A2, A3 and A4 first (A4 needs A3), B1 next because it decides B2, then C1. C2 and D3 wait for
real lab demand and a server budget.

## Questions for the founders

1. **Who pays for AI?** Each person's own key (today), a lab key set by the PI, or AI included in
   our price?
2. **Participant data:** is a flag that people set, plus a warning scan, enough for your ethics
   board, or should flagged files be blocked from upload altogether?
3. **Sending lab content to Anthropic:** are you comfortable with documents and files (never
   participant data) going to Anthropic's API when someone asks Claude about them?
4. **Budget:** a second server for the analysis runner (C2), and possibly Google's yearly security
   assessment (B5).
5. **MATLAB:** how many of our first labs rely on MATLAB toolboxes that Octave lacks? That decides
   whether D3 is ever worth building.

## Sources

- MathWorks MATLAB MCP Core Server and its licence terms: https://github.com/matlab/matlab-mcp-core-server
- Google Drive scopes (`drive.file`, restricted scopes): https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Picker and folder access (forum reports, not official): https://groups.google.com/g/google-apps-script-community/c/_W-NKbttfbo
