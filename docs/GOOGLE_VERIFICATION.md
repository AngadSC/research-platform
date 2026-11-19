# Google OAuth verification readiness (17 Nov 2026)

Assessment of origin/main 87aff59 (deployed on labbenchos.com). Sources: a read-only code audit with file:line
evidence, 293 focused backend tests (all pass, EXIT=0, Google mocked, nothing run against live Google), the live
homepage, /privacy and /terms, and Google's official documentation (links at the end). Paths: B = backend/,
F = frontend/src/.

**Update (branch night/g-int):** the fixes in section 4 marked DONE are in the code, and this text now describes
the code after them. Where a section still shows what the audit found, it says "before" or "was".

Labels: **CONFIRMED PASS**, **CONFIRMED GAP**, **NOT VERIFIED** (needs console or production), **RECOMMENDATION**.

## 1. Verdict

**Drive, Calendar and Meet** can be verified once the confirmed gaps below are fixed. They use one non-sensitive
scope (drive.file) and Calendar scopes that need ordinary sensitive-scope review (no security assessment).

**Google Chat** uses `chat.messages`, a **restricted** scope. A public (External, In production) app needs
restricted-scope verification **plus an annual third-party security assessment (CASA)**, because messages are stored
on our servers. Exceptions: apps used only inside one Workspace organisation (Internal), testing, or personal use
(a few known users, unverified screen, 100-user cap).

**Blockers (CONFIRMED GAP; 1 to 4 are DONE, see section 4):**
1. Privacy policy says nothing about Google Chat and is incomplete for Drive and Calendar (F pages/landing/pages/LegalPages.tsx:61-95, dated Nov 12, before Chat shipped Nov 15).
2. Homepage shows placeholders: "Trusted by research groups at" with four "[Institution logo]" boxes and a bracketed customer quote (F pages/landing/MarketingHome.tsx:119-133, 414-420, 443). Google requires the homepage to accurately represent the app.
3. Two in-app or public claims are false: "For linked files we only read details such as titles and modified times" (F pages/IntegrationsPage.tsx:138) and "It never copies your data out of these services" (F pages/landing/pages/FeaturesPage.tsx:372-373). The assistant reads Drive contents, code execution copies files to Anthropic, Edit in Google uploads files, Calendar and Chat write.
4. Data Access in the console did not list the Chat scopes (only drive.file, calendar.events, calendar.app.created were added).
5. Branding not verified; domain ownership in Search Console NOT VERIFIED.

**Strongly recommended before submitting** (reviewers ask "why not narrower?"; 6 to 8 are DONE):
6. Calendar push started by itself after connecting. Now off by default, and the settings row is made only when the person changes a setting; migration `labs/0023` switched push off on rows made before.
7. Declining any one permission connected nothing, and Calendar's identity depended on Drive. Now each of Drive and Calendar connects when its own scopes were granted (the person is told what was skipped), and Calendar names the account by OpenID userinfo.
8. Chat directory and membership lookups were mandatory. Now `chat.memberships.readonly` and `directory.readonly` are optional scopes: the account connects without them and the code skips those lookups.

## 2. Inventory

Tags: **[S]** our server calls Google; **[B]** browser code calls Google; **[E]** we only open Google's own page (frame or link), no token or content passes through us.

| Feature | Google calls | Client env var | Scopes | Data | Refs |
|---|---|---|---|---|---|
| Sign-in | [B] accounts.google.com redirect, [S] token exchange in allauth | `GOOGLE_CLIENT_ID/SECRET` | openid, email, profile (online, S256 PKCE since the fixes; **no PKCE** before) | Creates or links the user; ID-token claims in `SocialAccount.extra_data`; no tokens stored | B config/settings.py:322-341 |
| OAuth start, callback, refresh, revoke | [B] `/o/oauth2/v2/auth` (S256 PKCE, state, `access_type=offline`, `prompt=consent`), [S] `/token`, `/revoke` | Drive bundle: `GOOGLE_DRIVE_CLIENT_*`; Chat: `INTEGRATION_GOOGLE_CHAT_CLIENT_*` | per provider | State in session (single use, 600 s); tokens Fernet-encrypted (`INTEGRATION_ENCRYPTION_KEYS`, rotation command) | B integrations/services.py:101-229, 351-385, 473-491 |
| Drive identity | [S] `GET drive/v3/about?fields=user(permissionId,emailAddress)` | Drive | drive.file | permissionId, email | providers/google_drive.py:34-37, 104 |
| Calendar identity | [S] `GET openidconnect.googleapis.com/v1/userinfo` (before: Drive `about`, so Calendar failed if Drive was declined) | Drive client | openid, userinfo.email | email (the account id) or `sub` | providers/google_calendar.py |
| Picker | [B] `apis.google.com/js/api.js`, Picker with `setAppId`, `setDeveloperKey`, `setOAuthToken`; views: mine, shared with me, shared drives | key `GOOGLE_DRIVE_API_KEY`, app id `GOOGLE_DRIVE_APP_ID` | token carries the whole bundle (Drive + Calendar) | token via `GET labs/<id>/integrations/google/picker-token/` (no-store, audited, 30/h) | F lib/drive.ts:42-101; B integrations/views.py:217-266 |
| Link a Drive file | [S] `files.get` (metadata, `supportsAllDrives=true`) | Drive | drive.file | Title, type, URL, version stored; visible to the project. The person is asked whether the file identifies participants, and the answer is stored as the "contains participant data" mark (the AI tools refuse marked files) | providers/google_drive.py:40-77 |
| Daily freshness check | [S] `files.get` with the linker's token, 02:00 | Drive | drive.file | link status, version | B integrations/services.py:928-1049 |
| Edit in Google | [S] multipart upload with conversion to Docs/Sheets/Slides (5 MB cap) | Drive | drive.file | File bytes to the person's own Drive; flagged copies keep the flag; audited | providers/google_drive.py:120-194; B documents/services.py:420-475 |
| Statistics "Send to Sheets/Drive" | [S] same upload | Drive | drive.file | Result file to the person's Drive; audited | B documents/services.py:488-548 |
| Google editor panel | [E] iframe of docs.google.com `/edit` or `/preview` | none | none | URL only | F components/shared/GoogleEditorPanel.tsx:222 |
| AI `read_file` (in-app and MCP) | [S] `files.get`, then `/export` (text/plain, text/csv) or `alt=media` (20 MB cap) | Drive, asker's own token | drive.file | **Contents go to the AI provider (user's or lab's own key) or an MCP client.** Flagged items refused before any Google call | B assistant/drive_files.py:41-68; assistant/tools.py:1315-1338 |
| AI code execution | [S] same read, then Anthropic Files API upload and delete | Drive | drive.file | **Bytes copied into Anthropic's sandbox** | B assistant/code_exec.py:323-334, 399-416 |
| Meet meeting | [S] `POST calendars/primary/events?conferenceDataVersion=1&sendUpdates=none` (hangoutsMeet create request), PATCH, DELETE | Drive client | calendar.events | Title, times, members' emails to Google; stores event id and join URL | B labs/video_calendar.py:99-191 |
| Google events shown in the app | [S] `GET calendars/primary/events` (250 max) | Drive client | calendar.events | Read live, never stored, owner only; on by default | video_calendar.py:232-281 |
| App calendar push (15 min) | [S] `POST /calendars` ("labbenchos: <lab>"), events insert/patch/delete on that calendar | Drive client | calendar.app.created | Task, deadline and meeting titles, project name, join link; **off until the person turns it on** (was on by default) | video_calendar.py:287-441 |
| Meet API, freebusy, calendarList | none | | | | grep |
| Chat identity | [S] `GET openidconnect.googleapis.com/v1/userinfo` | Chat | openid, userinfo.email | `sub` (maps senders to members), email | B integrations/providers/google_chat.py:94-111 |
| Chat space picker | [S] `GET chat/v1/spaces`, `spaces/{id}/members`, People `batchGet` | Chat | chat.spaces.readonly; optional: chat.memberships.readonly, directory.readonly (their calls are skipped when declined) | names cached 10 min | B labs/google_chat.py:114-248 |
| Chat link | [S] `GET spaces/{id}` | Chat | chat.spaces.readonly | `GoogleChatBridge`; every member sees the space name | google_chat.py:266-308 |
| Chat poller (15 s) | [S] `GET spaces/{id}/messages` (createTime filter) | Chat, linker's token | chat.messages | Stores messages (4000 chars), sender name, avatar URL; whole lab or project sees them | google_chat.py:601-794 |
| Chat post | [S] `POST spaces/{id}/messages` as the author, else relayed via the linker as "*Name (email)* via labbenchos" | Chat | chat.messages | Member's message and, when relayed, their name and **email** (the email is the anchor: a display name is the member's own choice) | google_chat.py:367-448 |
| Chat delete | [S] `DELETE spaces/{id}/messages/{id}` (only ours) | Chat | chat.messages | | google_chat.py:451-481 |
| Chat thread import | [S] `GET messages` (500 to 1000) | Chat, importer's token | chat.messages | Thread (or the latest messages, up to 1000) copied into the lab or project chat as messages, outsiders' names included; audited | google_chat.py:830-967 |
| Directory names | [S] `GET people:batchGet?personFields=names,photos` (domain profile) | Chat | directory.readonly | names and photo URLs cached 24 h per lab | google_chat.py:151-197, 498-573 |
| Link previews of Google URLs | none (card or icon only, never fetched) | | | | F components/shared/LinkCard.tsx:29-30 |

**Cloud projects:** the sign-in client id starts `6680462925-` (public in `/_allauth/browser/v1/config`), probably the project number. Whether the Drive and Chat clients are in the same project is NOT VERIFIED (separate client ids do not prove separate projects).

## 3. Scopes: verdict per scope

| Scope | Class (Google docs) | Used for | Verdict |
|---|---|---|---|
| openid, email, profile (sign-in) | non-sensitive | sign-in | **KEEP** |
| drive.file | non-sensitive | `about`, metadata, export, download, upload on picked or app-created files (shared drives via Picker + `supportsAllDrives`) | **KEEP**. Do not widen: the two known limits (participants link health on pasted IDs; the assistant can't read files another member picked) are product limits, not reasons for a broader scope |
| calendar.events | sensitive (per console; Google's scope page does not label it) | events on `primary` only | **NARROW → calendar.events.owned** (every call uses `calendarId=primary`). INVESTIGATE with a real account that listing still shows events you were invited to; if not, the "Google events in the app" view loses invitations (tradeoff) |
| calendar.app.created | check console | the app's own calendar | **KEEP** |
| Meet API scopes | | Meet links come from Calendar `conferenceData` | none needed: **CONFIRMED PASS** |
| openid, userinfo.email (Chat; also on the Drive/Calendar client, to name the Calendar account) | non-sensitive | Chat: sender mapping by `sub`; Calendar: account identity | **KEEP** |
| chat.messages | **restricted** | list, post, delete messages | **KEEP** for current features. Narrower split (`chat.messages.readonly` restricted + `chat.messages.create` sensitive) is still restricted, so it doesn't avoid the assessment. Only dropping message reading (the sync and import) would |
| chat.spaces.readonly | sensitive | list and get spaces | **KEEP** |
| chat.memberships.readonly | sensitive | naming DMs and group chats in the picker; sender-name fallback | **OPTIONAL (DONE)**: declining it still connects; unnamed group chats are named by kind and date |
| directory.readonly | check console (People API) | sender names and photos | **OPTIONAL (DONE)**: declining it still connects; senders show as "Someone on Google Chat" |

Bot-based alternative: a Chat app with `chat.bot` (non-sensitive) only sees messages that mention it; reading a whole space as an app needs `chat.app.*` scopes that require each Workspace admin's approval. That does not fit "sync the whole lab space", so the user-authorized design stays; the price is restricted-scope review.

## 4. Application fixes, in order

| # | Status | Fix | Where |
|---|---|---|---|
| 1 | DONE | Rewrite the Google section of the privacy policy: a Chat section (scopes, what is read every 15 s, imports, posting as the member, relayed posts showing name and email, directory and membership lookups, storing non-members' names and photo URLs, who in the lab sees it); Calendar (members' emails sent as attendees, the app calendar, what stays in Google after disconnect); Drive (titles visible to the project, daily metadata check, Send to Sheets/Drive, AI reads including MCP and code execution copies to the AI provider); retention and deletion; keep the Limited Use statement and add the Workspace AI/ML affirmation (no training of generalized models). Update the date. Done; the Chat "Posting" bullet says relayed posts show name and email | F pages/landing/pages/LegalPages.tsx |
| 2 | DONE | Remove the placeholder logos and quote (or replace with real, permitted content). Removed | F pages/landing/MarketingHome.tsx |
| 3 | DONE | Correct the two false claims; add a one-line disclosure per service next to Connect. Both claims corrected | F pages/IntegrationsPage.tsx:138, 402-470; F pages/landing/pages/FeaturesPage.tsx:372-373 |
| 4 | DONE | Calendar push off by default; create the sync row only when the person turns it on. Migration `labs/0023` also switches push off on rows made before (nothing already in Google is deleted) | B labs/models.py; B labs/video_calendar.py; B labs/migrations/0023_calendar_push_off_by_default.py |
| 5 | DONE | Relayed Chat posts keep the email: `*Name (email)* via labbenchos: text` (the original D317 security choice, because a display name is the member's own choice); "via LabBench" changed to "via labbenchos"; the sync dialog and the privacy policy say that relayed posts show name and email; link-preview user agent says labbenchos | B labs/google_chat.py `_relayed`; F pages/GoogleChatSync.tsx; F pages/landing/pages/LegalPages.tsx; B core/link_preview.py |
| 6 | DONE | Import dialog: say who will see the imported thread | F pages/GoogleChatImport.tsx |
| 7 | DONE | Partial grants: keep each bundle member whose scopes were granted and say what was skipped; give Calendar its own identity (add openid email, use userinfo, not Drive `about`); make Chat's directory and membership scopes optional; update docs/SETUP_GOOGLE_ZOOM.md. Done; extra scopes are still refused, and revoking at Google now also checks bundle siblings in other labs | B integrations/services.py; providers/google_calendar.py; providers/google_chat.py |
| 8 | OPEN | Narrow `calendar.events` to `calendar.events.owned` (after the invite-listing check) | providers/google_calendar.py:20 |
| 9 | OPEN | Picker token: drive.file only (INVESTIGATE whether a refresh with a narrower scope is accepted) or unbundle Drive and Calendar; fix the scope it reports | B integrations/services.py:215-227; views.py:255-263 |
| 10 | OPEN | Retention: on disconnect clear `external_email` and `granted_scopes`, delete calendar sync rows, offer to delete the app calendar; document what remains; add account deletion | B integrations/services.py:445-556 |
| 11 | DONE | Sign-in PKCE: `"OAUTH_PKCE_ENABLED": True` under `SOCIALACCOUNT_PROVIDERS["google"]` | B config/settings.py |
| 12 | DONE | Ask "contains participant data?" when a file is linked from Drive (the assistant can read it); the answer is stored as the mark (amends D257) | F components/shared/FromDriveButton.tsx; B documents/services.py |
| 13 | DONE | Participants link health: say "Pick this file with From Drive to check it" instead of "not found"; the cell panel has a From Drive button | B participants/services.py; F pages/project/participants/CellPanel.tsx |
| 14 | DONE (code comments; D64's own wording stays as history) | Fix stale comments that say "never alt=media or export" | providers/google_drive.py; providers/__init__.py |
| 15 | OPEN (console) | Product decision: put the Chat client in its **own Cloud project**, so Chat's restricted-scope review and assessment never hold up Drive and Calendar verification. Keep it in Testing (pilot users as test users) until you choose CASA or Internal | console + `INTEGRATION_GOOGLE_CHAT_CLIENT_*` |

**CONFIRMED PASS:** integration OAuth state and S256 PKCE, provider taken from stored state, extra scopes refused; tokens encrypted with rotation; refresh under a row lock, `invalid_grant` handled; revoke on disconnect, member removal and deactivation (atomic, with a daily orphan sweep), never revoking a grant another lab or person still uses; Picker token endpoint audited, throttled, no-store; no tokens or content in logs; participant flag enforced before any Google call by AI tools; Chat and meetings kept out of AI tools; Google URLs never fetched for previews; CSP limited to the Google hosts used.

## 5. Google Cloud Console checklist

Fill placeholders from the console: project number (Cloud overview), client ids (Google Auth Platform → Clients).

### A. What matches the code TODAY (do this now)

For the project holding `<SIGN_IN_CLIENT_ID>` and `<DRIVE_CLIENT_ID>` (and the Chat client if it is in the same project):

1. **APIs & Services → Enabled APIs**: Google Drive API, Google Picker API, Google Calendar API, Google Chat API, People API.
2. **Chat API → Configuration**: app name "labbenchos", avatar URL, description; Interactive features **off**; Visibility: the pilot users or domain. Save (Google refuses all Chat calls until saved).
3. **Branding**: app name **labbenchos** (exactly as on the site); support email; logo; Application home page `https://labbenchos.com`; Privacy policy `https://labbenchos.com/privacy`; Terms `https://labbenchos.com/terms`; Authorized domain `labbenchos.com`; developer contact email.
4. **Domain**: verify `labbenchos.com` in Google Search Console (DNS TXT record) signed in as an Owner or Editor of the Cloud project.
5. **Clients** (type Web application each):
   - Sign-in client: redirect URI `https://labbenchos.com/accounts/google/login/callback/` (and `http://localhost:5173/accounts/google/login/callback/` for local).
   - Drive/Calendar client: `https://labbenchos.com/api/integrations/oauth/callback/` (and localhost). JavaScript origin `https://labbenchos.com` (harmless; whether the Picker needs it is unconfirmed).
   - Chat client: the same integrations callback.
   - If one client serves sign-in and integrations, register both redirect URIs on it.
6. **Picker**: `GOOGLE_DRIVE_APP_ID` must be the project number of the project that owns the Drive client; restrict `GOOGLE_DRIVE_API_KEY` to the Google Picker API and HTTP referrer `https://labbenchos.com/*`.
7. **Data Access → Add or remove scopes**, exactly what the code requests today:
   - Sign-in client: `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`
   - Drive/Calendar client: `openid`, `.../auth/userinfo.email` (they name the Calendar account), `.../auth/drive.file`, `.../auth/calendar.events`, `.../auth/calendar.app.created`
   - Chat: `openid`, `.../auth/userinfo.email`, `.../auth/chat.messages`, `.../auth/chat.spaces.readonly`; optional (the person may untick them): `.../auth/chat.memberships.readonly`, `.../auth/directory.readonly`
8. **Audience**: External. For the pilot: **Testing**, add every pilot user under Test users (max 100). They see an "unverified" warning and click Continue. Publish to production only when you submit for verification.
9. **Verification Center**: submit when sections 4.1-4.6 are live, with the justifications (section 6) and the demo video (section 7).

### B. AFTER the recommended code changes are deployed and tested (not before)

1. Replace `calendar.events` with `calendar.events.owned` in Data Access (only after the code stops requesting `calendar.events`).
2. `directory.readonly` and `chat.memberships.readonly` are already optional in the code: say so in their justifications (or remove them from Data Access if you accept the fallbacks).
3. If the Chat client moves to its own project: create project `labbenchos-chat`, enable Chat API and People API, configure the Chat app there, add only the Chat scopes, keep it in Testing until CASA or Internal, and put its client id and secret in the server's `INTEGRATION_GOOGLE_CHAT_CLIENT_*`; then remove the Chat scopes and Chat API from the main project.

## 6. Draft justifications (each under 1,000 characters; honest to the current code)

**calendar.events** (or calendar.events.owned after fix 8): labbenchos is a research-lab workspace. When a lab member schedules a lab meeting, labbenchos creates the event on that member's own primary Google Calendar with a Google Meet link (events.insert with conferenceData), and updates or deletes it when the meeting is changed or cancelled in labbenchos. It also lists the member's upcoming primary-calendar events so they appear, to that member only, in the labbenchos calendar; they are read live and never stored. calendar.app.created alone cannot do this because these events must be on the member's own calendar where they and invited lab members see them. We do not read other calendars, calendar lists or free/busy.

**calendar.app.created**: labbenchos keeps one secondary calendar per lab ("labbenchos: <lab name>") that it creates in the member's account, and adds, updates and removes events on it for the member's task deadlines, project deadlines and lab meetings, only when the member turns sync on. It never touches any other calendar through this scope.

**chat.messages** (restricted): a lab can link its labbenchos lab chat to one Google Chat space the linking member belongs to. labbenchos lists new messages in that space every 15 seconds to show them in the lab chat, posts each lab-chat message to the space as its author (for a member who has not connected Chat, through the linking member's connection, headed by that member's name and email and "via labbenchos"), and deletes a message in the space when its author deletes it in labbenchos. Whoever may link a chat can also copy one thread they can read (or a conversation's latest messages, up to 1000) into the lab or project chat. Messages are stored only to show them to members of that lab or project and are never used for AI or advertising. chat.messages.readonly plus chat.messages.create would not cover deleting our own posts, and both read scopes are restricted anyway.

**chat.spaces.readonly**: used to list the Google Chat spaces the member belongs to, so they can pick which space to link or import from, and to read the linked space's name. No space settings are changed.

**chat.memberships.readonly** (if kept): used to show readable names for unnamed group chats and direct messages in the space picker, and as a fallback to name message senders. It is read only.

**directory.readonly** (if kept): used to show the names and profile photos of message senders from the member's own Google Workspace directory, so synced and imported messages show who wrote them instead of an id. Results are cached for 24 hours. If the member declines it, senders show as "Someone on Google Chat".

## 7. Demo video script (one unlisted YouTube video per client, English UI, dummy accounts)

Use a dummy Workspace account (for example `pilot.pi@<test-domain>`) and the fake lab "Example Cognition Lab (FAKE)" with fake data only. Before each consent screen, pause on the browser address bar so the `client_id=` value is readable, then show the consent screen with the app name "labbenchos".

**Video 1, Drive, Calendar and Meet (Drive client)**
1. Sign in to labbenchos (show the sign-in consent: basic profile only).
2. Settings → Integrations → Google Drive → Connect. Show the URL with `client_id`, the consent screen listing Drive (files you use with this app) and Calendar permissions. Allow.
3. Drive (drive.file): in a project, From Drive → the Google Picker opens → pick one fake CSV → it appears linked. Open it in the side panel (Google's own editor). Upload a fake .docx → Edit in Google → a Google Doc copy is created in the account. Run Statistics on a fake file → Send to Google Sheets → the Sheet appears in Drive. Ask the assistant to read the linked fake file (shows contents read only on request).
4. calendar.events: Calendar → schedule a lab meeting with a Meet link → open Google Calendar in another tab and show the event with the Meet link on the primary calendar. Edit the time in labbenchos → the event moves. Cancel → it is removed. Show the member's own Google events appearing in the labbenchos calendar.
5. calendar.app.created: Calendar settings → turn on sync → Sync now → show the "labbenchos: Example Cognition Lab (FAKE)" calendar in Google Calendar with a fake task deadline.
6. Disconnect in Integrations → show the connection removed (and, optionally, myaccount.google.com/permissions no longer listing it).

**Video 2, Google Chat (Chat client)**
1. Settings → Integrations → Google Chat → Connect. Address bar with `client_id`, consent screen with the Chat permissions. Allow.
2. chat.spaces.readonly (+ memberships): Lab chat → Sync with Google Chat → the list of spaces the account is in → pick a fake test space.
3. chat.messages: post "Hello from labbenchos" in the lab chat → it appears in the Google Chat space as the member. Post in Google Chat → it appears in the lab chat within 15 s with the sender's name (directory.readonly). Delete the labbenchos post → it disappears from Google Chat.
4. Import: in a project chat, Import from Google Chat → choose the space and a thread → the messages appear in the chat with names and times.
5. Unlink the space and disconnect.

## 8. Acceptance tests

Permissions and consent
- Connect Drive and Calendar declining one permission: only the granted service connects, and the person is told which was skipped and how to add it. Declining every permission of both connects nothing.
- Disconnecting Calendar in one lab never revokes a grant that a Drive row in another lab still uses.
- A member, a viewer and a PI can connect their own accounts; nobody can use another member's token (existing test `test_no_google_connection_never_borrows_another_members`).
- Picker shows only the person's own and shared files; a file not picked can't be read by the assistant.
- A flagged file or folder is refused by AI tools before any Google call (existing tests).

Functionality (live, with a dummy Workspace account; not covered by mocked tests)
- Drive `about` works with drive.file only.
- Picker works with the configured key and app id; shared-drive files can be linked and read.
- Meet event created, moved and deleted on primary; app calendar created and filled only after sync is turned on.
- Chat: link a space, both directions within 15 s, delete sync, thread import into a chat with names.

Data lifecycle
- Disconnect revokes at Google (myaccount permissions page) unless another lab still uses the same grant.
- Removing a member revokes their accounts in the same transaction (existing test) and stops their Chat link (existing test).
- After disconnect: what remains (Chat messages, Drive titles, app calendar in Google) matches what the privacy policy says.
- Token encryption key rotation command re-encrypts all rows (existing test).

## 9. Facts still needing console or production inspection

- Whether the Drive, Chat and sign-in clients are in one project or several; the project number for the Picker app id.
- Consent screen type and publishing status; the test-user list.
- Scope classification shown in Data Access for calendar.events, calendar.app.created, directory.readonly.
- Branding verification and Search Console domain ownership.
- Production `FRONTEND_URL` and proxy headers (both redirect URIs depend on them).
- The Picker API key's restrictions.
- Whether the University of Alberta (or each pilot university) blocks unverified third-party apps.
- Whether Chat membership `displayName` is filled under user authentication.

## Sources

- Choose Chat API scopes and classifications: https://developers.google.com/workspace/chat/authenticate-authorize
- Drive scopes (drive.file non-sensitive): https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Calendar scopes: https://developers.google.com/workspace/calendar/api/auth
- Meet links via Calendar conferenceData: https://developers.google.com/workspace/calendar/api/guides/create-events
- Sensitive-scope verification (justification, video): https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- Restricted-scope verification and security assessment: https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification
- Verification requirements (homepage, privacy policy, domains): https://support.google.com/cloud/answer/13464321
- Unverified apps and the 100-user cap: https://support.google.com/cloud/answer/7454865
- Workspace API user data and developer policy (AI/ML, Limited Use): https://developers.google.com/workspace/workspace-api-user-data-developer-policy
- Google API Services User Data Policy: https://developers.google.com/terms/api-services-user-data-policy
