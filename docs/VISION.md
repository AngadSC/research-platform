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

### Phase S: subscription first (now)
Nobody pays for AI yet, so for now Claude runs on each person's own Claude plan, in Anthropic's apps,
reaching labbenchos through our connector. Everything here costs us nothing per use.

| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| S1 | File links for tools on the person's computer: `get_file_link` (short-lived download link to one file, permission-checked, refuses flagged files) and `create_upload_link` (one-time upload into a project, size and type limits, optional link to an Analysis). Both are audited and expire within 15 minutes. Needs A3 | M | opus / high | todo |
| S2 | Results appear right away: the project's files, analyses and documents refresh on their own while open (polling, about every 10 seconds) and show a "New from Claude" notice | S | sonnet / medium | todo |
| S3 | MATLAB on your own computer: a help page and a one-page setup for Claude Desktop with MathWorks' MATLAB MCP Core Server and the labbenchos connector. Claude fetches the lab file with S1, runs MATLAB locally, and MATLAB uploads the figure and results with S1, so they show in the project within seconds | S | sonnet / medium | todo |
| S4 | Claude in Chrome: Anthropic's Chrome extension opens a Claude side panel on any site, labbenchos included, on the person's own plan. Test our main pages with it, fix anything it cannot read or click, and add a help page. This is the side panel we can offer today without paying for AI | S | sonnet / medium | todo |

### Phase A: quick wins (do first)
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| A1 | Integrations link in every member's sidebar; pointer to Claude and ChatGPT setup | S | orchestrator | done |
| A2 | Later, needs paid AI. Docked Claude panel: right side, stays open across pages, resizable and collapsible, remembers its state per browser, sends the current page as context; keyboard shortcut; phone keeps the full-screen sheet | M | sonnet / medium | todo |
| A3 | Participant-data flag on files, folders, datasets and documents; asked on upload, copied down from folders; every AI tool, AI search and the MCP server refuse flagged items; tests in the permission matrix | M | opus / high | todo |
| A4 | AI file tools: `list_files`, `read_file` (PDF, Word, Excel or CSV, text, images) with size limits and untrusted-content wrapping; refuses flagged files (needs A3) | M | opus / high | todo |
| A5 | Later, needs paid AI. Lab AI key: a PI or lab admin sets one key for the lab, with a monthly spending cap and per-person usage shown; a person's own key still wins | M | sonnet / medium | todo |

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
| C1 | Later, needs paid AI. Claude runs Python with Anthropic's code-execution tool on chosen, unflagged files; figures and tables are saved back to the project; each run becomes an Analysis in lineage with its code and inputs | L | opus / high | todo |
| C2 | Our own runner on a separate server: Python, R and Octave in locked-down containers (gVisor, no network, CPU, memory and time limits); same UI as C1; security review before launch | L | opus / high | todo |
| C3 | Analyses page: list runs per project, open outputs, rerun on a newer dataset version, download the code | M | sonnet / medium | todo |

### Phase D: MATLAB
| ID | Task | Size | Model / effort | Status |
|---|---|---|---|---|
| D1 | Help page: use your own MATLAB with Claude Desktop (MathWorks' MATLAB MCP Core Server) together with the labbenchos connector | S | haiku / low | todo |
| D2 | Octave in the C2 runner for `.m` scripts | S | sonnet / medium | todo |
| D3 | Optional, only if labs ask: a small helper app that links a person's own MATLAB to the in-app Claude panel | L | opus / high | todo |

Order (revised after the founders' answers below): A3 first, because S1 and A4 both need the
participant-data flag. Then Phase S and A4, then B1, which decides B2. A2, A5 and C1 need an API key,
so they wait until labs pay for AI. C2 waits for a server budget.

## Founders' answers (2026-11-11)

1. **Who pays for AI:** nobody yet. For now Claude runs on each person's own Claude subscription
   (Phase S). Later labs will pay for AI through us, which unlocks A2, A5 and C1.
2. **Participant data:** default decision, since nothing changes for users who never upload it.
   People can upload a file with participant information only if they tick "Contains participant
   data". Claude never sees ticked files, and we keep recommending that raw participant data stays
   in the institution's approved systems (SPEC section 1). Each lab confirms with its own ethics board.
3. **Sending lab content to Anthropic:** up to each person. Nothing is sent unless they ask Claude
   about it, and flagged participant data is never sent.
4. **Costs:**
   - Now: nothing extra. Phase S runs on people's own Claude plans and their own MATLAB.
   - Analysis server (C2, later): today's server has 2 CPUs and 4 GB of memory with about 1.9 GB
     free. That is fine for the website but not for running analyses too. A second server with
     4 CPUs and 8 GB is roughly CA$30 to $60 a month (an estimate; check CanHost's prices).
   - Google's full-Drive permission (B5, probably never): a yearly third-party security assessment,
     an estimated several hundred to a few thousand US dollars a year plus weeks of work. Not
     needed while picking files works.
   - AI through us (later): charged per use by Anthropic. Measure real use in a pilot before
     setting lab prices.
5. **MATLAB:** universities give everyone a MATLAB licence, so it runs on each person's own
   computer (S3). Results reach the website through upload links (S1) and show up right away (S2).
   Octave on our server (D2) is only a fallback for people without MATLAB.

## Sources

- Claude in Chrome: https://claude.com/chrome
- MathWorks MATLAB MCP Core Server and its licence terms: https://github.com/matlab/matlab-mcp-core-server
- Google Drive scopes (`drive.file`, restricted scopes): https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Picker and folder access (forum reports, not official): https://groups.google.com/g/google-apps-script-community/c/_W-NKbttfbo
