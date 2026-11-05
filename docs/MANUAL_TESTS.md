# Manual tests with real Google credentials

Everything automated uses mocks. This checklist is for a person with a Google account, to confirm Google sign-in and Google Drive really work. Use a throwaway Google account (or a test user on the consent screen), never a production lab. Local app: `http://localhost:5173`.

## 1. Google Cloud setup

1. Open Google Cloud Console and create a project (for example "research-platform-dev"). Note its **project number** (Dashboard > Project info). That is `GOOGLE_DRIVE_APP_ID`.
2. APIs and Services > Library: enable **Google Drive API** and **Google Picker API**.
3. APIs and Services > OAuth consent screen:
   - User type External, publishing status **Testing**. Add your test Google account(s) under Test users.
   - Scopes: add **`https://www.googleapis.com/auth/drive.file`** for the integration. For sign-in only `openid`, `email`, `profile`. Add nothing else. Never `drive` or `drive.readonly` (D64).
4. APIs and Services > Credentials > Create credentials > OAuth client ID, type **Web application**, twice (D66 keeps them separate):
   - **Sign-in client.** Authorized redirect URI: `http://localhost:5173/accounts/google/login/callback/`. Copy its ID and secret to `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
   - **Drive client.** Authorized redirect URI: `http://localhost:5173/api/integrations/oauth/callback/`. Copy its ID and secret to `GOOGLE_DRIVE_CLIENT_ID` / `GOOGLE_DRIVE_CLIENT_SECRET`.
   - (One client for both also works if you register both redirect URIs on it.)
5. Credentials > Create credentials > **API key**. Restrict it: Application restrictions "Websites" with `http://localhost:5173/*`; API restrictions "Google Picker API". Copy it to `GOOGLE_DRIVE_API_KEY`. It is public by design (the browser sends it).
6. Put all six values in `.env` (see `.env.example`), then restart: `docker compose up -d --force-recreate backend worker beat`.

```
GOOGLE_CLIENT_ID=            GOOGLE_CLIENT_SECRET=
GOOGLE_DRIVE_CLIENT_ID=      GOOGLE_DRIVE_CLIENT_SECRET=
GOOGLE_DRIVE_API_KEY=        GOOGLE_DRIVE_APP_ID=<project number>
```

For production use your own domain in every URI (`https://<domain>/accounts/google/login/callback/` and `https://<domain>/api/integrations/oauth/callback/`), the same variables in `deploy/.env.prod`, and check the Caddy CSP in `deploy/Caddyfile` allows the Picker (apis.google.com, gstatic.com, docs.google.com, content.googleapis.com). If the Picker opens blank in production, read the browser console for the blocked host and add it.

## 2. Google sign-in

- [ ] Login page shows "Continue with Google". With `GOOGLE_CLIENT_ID` empty it is hidden.
- [ ] Sign in with the test account. You land signed in; a new account is created or the existing one with that email is linked (only for `@gmail.com`, or a Workspace domain that matches, D73).
- [ ] Security page lists Google as connected; Disconnect works (asks for your password first, D74).

## 3. Drive is hidden until configured

- [ ] With `GOOGLE_DRIVE_API_KEY` or `GOOGLE_DRIVE_APP_ID` empty: no "Link from Google Drive" button anywhere (Files tab, dataset, analysis, result, manuscript).
- [ ] With `GOOGLE_DRIVE_CLIENT_ID` empty: Settings > Integrations says "Not set up for your institution".

## 4. Connect Drive

- [ ] Lab > Settings > Integrations > Connect on Google Drive.
- [ ] The consent screen asks only to "See, edit, create and delete only the specific Google Drive files you use with this app". Nothing broader.
- [ ] You return to Integrations with "Google Drive connected" and your email shown, status Active.
- [ ] Connect again with a different Google account while this one is active: refused with "Another account is already connected" (D69).
- [ ] Network tab: no Google script was loaded yet on this page.

## 5. Pick and link

Make three files in the test Drive: a CSV, a Google Doc and a PDF.

- [ ] Project > Files > Link from Google Drive. Only now does the browser load `apis.google.com/js/api.js`. The Picker opens.
- [ ] Pick the CSV. A toast says it was linked. The row shows the Drive icon, the name, "Modified ... ago", "Linked by <you>", status "Up to date" and the line "Opening this file uses Google's own sharing settings."
- [ ] Clicking the name opens the file in a new tab. Inspect the anchor: `target="_blank"`, `rel="noopener noreferrer"`.
- [ ] Cancel the Picker: nothing happens, no error.
- [ ] Do the same from a dataset record, an analysis, a result and a manuscript (the "Linked files" section on each record page). Each shows only its own links.
- [ ] Pick the Google Doc: it links (no checksum, only a version).
- [ ] Network tab on the app domain: `GET .../integrations/google/picker-token/` returns `Cache-Control: no-store` and only an access token. No other response contains a token.

## 6. Dataset version

- [ ] Create a dataset record with an empty checksum. Link the CSV to it. The record's Checksum now reads `md5:<32 hex>` (compare with `md5sum` of the file). Version label is unchanged.
- [ ] Link the Google Doc to another empty record: checksum reads `drive-version:<n>`.
- [ ] Link a Drive file to a record that already has `sha256:...`: the toast says the record already has a different version and it was left alone; the checksum is unchanged.
- [ ] Project > Lineage > click that dataset node: the panel lists the Drive file with its status.

## 7. Refresh and change

- [ ] Click Refresh on a link: toast "Checked".
- [ ] In Drive, edit the file (upload a new version of the CSV). In the app click Refresh: the status becomes "Changed since linked" and Accept change appears. The dataset record's checksum is **not** modified.
- [ ] Accept change: status returns to "Up to date". Audit log shows `external_link.change_accepted`.
- [ ] Daily job: `docker compose exec backend python manage.py shell -c "from integrations.jobs import check_links; print(check_links())"` prints counts. Edit the file again, run it, reload: the status updates without clicking Refresh.

## 8. Delete and lose access

- [ ] Move the linked file to the Drive trash, click Refresh: "No longer available". Restore it and refresh: back to normal.
- [ ] Remove the test account's access to a file you shared from another account: Refresh shows "No longer available".

## 9. Disconnect and lab removal

- [ ] Disconnect Google Drive on the Integrations page. Status becomes revoked. At https://myaccount.google.com/permissions the app no longer has access (the revoke call worked). Links stay but show "Can't check: the linker's connection is inactive" with no Refresh button; the daily job skips them.
- [ ] Reconnect with the same account: the old links work again.
- [ ] As the PI, open "Everyone's connections", Revoke a member's connection: it is revoked and audited as `integration.revoked`.
- [ ] Remove a member who has Drive connected from the lab: their connection is revoked (Integrations list shows revoked) and their links stay. The Google grant is revoked only if no other lab uses the same Google account (D68).

## 10. Final sweep

- [ ] Audit log has `integration.connected`, `external_link.created`, `external_link.change_accepted`, `external_link.removed`, `integration.disconnected`, and no entry contains a token or URL query string.
- [ ] `git grep -n "drive.readonly\|auth/drive\b"` finds nothing except tests that assert they are refused.

# Manual setup: OneDrive, Dropbox and Box (D100 to D104)

Everything automated uses mocks; none of these three has been run against the real service. Use throwaway or test accounts, never a production lab. Redirect URI for all three: `http://localhost:5173/api/integrations/oauth/callback/` (production: `https://<domain>/api/integrations/oauth/callback/`). Put the values in `.env` (see `.env.example`), then `docker compose up -d --force-recreate backend worker beat`. Each provider shows "Not set up for your institution" until its client id is set.

## OneDrive and SharePoint

1. Microsoft Entra admin centre > App registrations > New registration. Supported account types: for personal and work accounts choose "Accounts in any organizational directory and personal Microsoft accounts" (tenant `common`); for one institution choose single tenant and set `INTEGRATION_ONEDRIVE_TENANT` to its tenant id or domain. Redirect URI: type **Web**, the URI above.
2. API permissions > Microsoft Graph > Delegated: **`Files.Read.All`** and **`offline_access`** only. Remove `User.Read` (added by default). If the tenant requires it, an admin grants consent.
3. Certificates and secrets > New client secret. Copy the secret value now.
4. `.env`: `INTEGRATION_ONEDRIVE_CLIENT_ID` (Application (client) ID), `INTEGRATION_ONEDRIVE_CLIENT_SECRET`, optionally `INTEGRATION_ONEDRIVE_TENANT`.
5. Checks:
   - [ ] Connect succeeds. If it fails with `unexpected_scope`, Microsoft added default scopes (for example `User.Read`, `openid`) to the grant: note the exact scopes in the audit log and raise it, do not widen the provider's scopes.
   - [ ] Search finds a file in your OneDrive and, with a work account, one in a SharePoint library and one shared with you; link each to the Files tab and to a dataset.
   - [ ] A business file shows the link as a SharePoint address, a personal file as `onedrive.live.com`. A dataset's empty checksum is filled for a file with a SHA-256 hash (usually personal) and left empty for quickXor-only files.
   - [ ] Edit the file, press Check: status becomes changed. Delete it (and empty the recycle bin) or remove your access: Check says unavailable.
   - [ ] Disconnect wipes the tokens but Microsoft keeps the grant (no revoke endpoint, D102): confirm the app still appears at `myapps.microsoft.com` and remove it there. Reconnect works.

## Dropbox

1. Dropbox App Console > Create app > **Scoped access** > **Full Dropbox** (or "App folder" for a narrower test). Name it. Settings > Redirect URIs: add the URI above.
2. Permissions: tick only **`account_info.read`** and **`files.metadata.read`**, then Submit. Do this before connecting: scopes are fixed when a person authorises.
3. Settings: copy App key and App secret. `.env`: `INTEGRATION_DROPBOX_CLIENT_ID` (App key) and `INTEGRATION_DROPBOX_CLIENT_SECRET`. The app stays in development status (up to 500 users) unless you apply for production.
4. Checks:
   - [ ] Connect succeeds; Settings > Integrations shows your Dropbox email.
   - [ ] Search by file name finds a file; link it to the Files tab and to a dataset. The dataset checksum becomes `dropbox-content-hash:<64 hex>`; the link opens the file's place in Dropbox.
   - [ ] Change the file, press Check: changed. Move the file within Dropbox: the id still resolves. Delete it: unavailable.
   - [ ] Disconnect: the app disappears from Dropbox > Settings > Connected apps (revoke works through the refresh-token trade, D103). The audit entry says `provider_revoked: true`.
   - [ ] No request to `content.dropboxapi.com` appears in the backend log (log lines show host and path only).

## Box

1. Box Developer Console > Create New App > **Custom App** > **User Authentication (OAuth 2.0)**.
2. Configuration: OAuth 2.0 Redirect URI = the URI above. Application Scopes: tick only **Read all files and folders stored in Box** (`root_readonly`); leave write, manage users, enterprise and webhooks unticked. Save.
3. Copy Client ID and Client Secret. `.env`: `INTEGRATION_BOX_CLIENT_ID` and `INTEGRATION_BOX_CLIENT_SECRET`. A work account in an enterprise may need the Box admin to authorise the app (Admin Console > Apps > Custom Apps Manager).
4. Checks:
   - [ ] Connect succeeds (account shows your Box login).
   - [ ] Search finds a file; link it. Paste `https://app.box.com/file/<id>` (from the browser address bar) as the address: it links the same file. A folder link or another host is refused.
   - [ ] A dataset's empty checksum becomes `sha1:<40 hex>`.
   - [ ] Upload a new version, press Check: changed. Trash the file: unavailable.
   - [ ] Disconnect: the app's access is revoked (Box > Settings > Integrations). Wait over an hour and reconnect to confirm refresh-token rotation works (Box refresh tokens are single use).

## REDCap (manual setup)

- [ ] Get a token: in the REDCap project, Applications > API > Request API token (an admin may have to approve it). The token belongs to that one project. Minimal right: the user right "API Export" only; do not tick API Import. We call only project information (`content=project`), never records, files, reports, the data dictionary or logs.
- [ ] Connect: Integrations > REDCap, enter your REDCap address (e.g. `https://redcap.example.edu/redcap`; `<address>/api/` must be the API) and the token. An http, IP or port address is refused before anything is sent. If the deployment sets `INTEGRATION_ALLOWED_INSTANCE_HOSTS`, the host must be in it.
- [ ] Search shows exactly one result: the token's project. Link it to a dataset record and to the project. "Open" goes to `<address>/index.php?pid=<id>`.
- [ ] In REDCap change the project title or move it to production; Refresh shows "Changed since linked". Add a record: nothing changes (by design).
- [ ] Regenerate the token in REDCap and Refresh: the link shows "No longer available" (REDCap answers 403).
- [ ] In REDCap's logging, every call from the app is "Export Project Information"; nothing else appears.

## Qualtrics (manual setup)

- [ ] Get a token: Qualtrics > Account Settings > Qualtrics IDs > API > Generate Token. Note your datacenter or brand host (e.g. `yourbrand.yul1.qualtrics.com`). The token acts as you: use an account that sees only the surveys to be linked, not an admin.
- [ ] Connect with that address and token. `https://qualtrics.com` and any host not under `.qualtrics.com` are refused (`instance_not_allowed`).
- [ ] Search by part of a survey name: matching surveys appear, newest change first. Link one to a dataset record and to the project; "Open" goes to `/survey-builder/<id>/edit`.
- [ ] Edit the survey and save: Refresh shows "Changed since linked". Collecting a response changes nothing here.
- [ ] Delete the survey: "No longer available".
- [ ] Only `whoami`, the survey list and `survey-definitions/<id>/metadata` are called; no response or export calls.

## protocols.io (manual setup)

- [ ] Get a token: protocols.io > your profile > Developer > the client access token for your own account. No special rights; it reads only what you can see.
- [ ] Connect with the token (no address). Search with an empty box lists your own protocols; with a word it also lists public matches.
- [ ] Paste `https://www.protocols.io/view/<slug>` of a protocol you can see and link it to an analysis, a document and the project. Title, version and DOI show; no steps or materials are fetched.
- [ ] Publish a new version of your protocol: Refresh shows "Changed since linked".
- [ ] Make a protocol unavailable to the account (or delete it): "No longer available". Revoke the token at protocols.io and Refresh: the connection shows as expired.
- [ ] Pasted addresses on other hosts (`protocols.io.evil.net`, `http://`) are refused.

## Zotero (manual setup, D115)

- [ ] At https://www.zotero.org/settings/keys/new create a key named "lab-test": allow library access (read only) for your personal library and the group(s) you want; do NOT tick write access. Save it.
- [ ] Integrations > Zotero > Connect, paste the key: connected, shows your Zotero user name.
- [ ] Create a second key with "Allow write access" ticked and try to connect with it: refused (the connection is not stored). Delete that key.
- [ ] On a decision, link Zotero: search for a word from an item title. Items from your library and from a group both appear.
- [ ] Link one item to a decision: its title, url and DOI appear in the decision's references and the toast says copied. Link the same item (or one with the same DOI) to the same decision again: no duplicate. Existing references are untouched.
- [ ] Edit the item in Zotero (change the title), Refresh the link: "Changed since linked". Delete the item (empty trash): "No longer available".
- [ ] Revoke the key at zotero.org: the next Refresh marks the connection expired.

## Zenodo (no account needed, D116)

- [ ] On a dataset record's links choose Zenodo and paste `https://zenodo.org/records/<n>` for a real public record, then `https://doi.org/10.5281/zenodo.<n>`: both link, title and version match the Zenodo page.
- [ ] A one-file record fills an empty dataset checksum with `md5:<hex>` (compare with Zenodo's file page); a many-file record shows `zenodo-manifest:...`. The dataset's version label is unchanged.
- [ ] A DOI with another prefix and a `zenodo.org/records/<n>/files/...` address are refused.
- [ ] Server side, only `zenodo.org/api/records/<n>` is requested; no file is fetched.

## Figshare (no account needed, D117)

- [ ] Paste a public article page, `https://figshare.com/articles/dataset/<title>/<id>`, then its `https://doi.org/10.6084/m9.figshare.<id>` DOI: both link; title, version and modified date match the article.
- [ ] Link to a dataset record with an empty checksum: it fills as for Zenodo.
- [ ] A private share link (`figshare.com/s/...`) is refused; an unpublished article is "not found".

## OSF (manual setup, D118)

- [ ] At https://osf.io/settings/tokens create a personal access token with only the `osf.full_read` scope. Do not tick any write scope.
- [ ] Integrations > Open Science Framework > Connect with the token: connected, shows your name.
- [ ] Paste `https://osf.io/<id>/` for one of your PRIVATE projects on a project's links: it links (title, modified date). Paste a project you cannot open: "not found".
- [ ] Link a file: paste `https://osf.io/<project id>/files/osfstorage/<24-hex file id>` (copy the id from the file's API address) to a dataset record with an empty checksum: it fills with `sha256:<hex>` and the version is the file's current version. **[H]** confirm that address form and the web link we store open the right page.
- [ ] Upload a new version of the file, Refresh the link: "Changed since linked". Revoke the token at OSF: the connection shows expired.

## GitHub (manual setup, D105 to D107)

Use a throwaway GitHub account or a test repository. No server settings are needed: the person pastes a token.

1. GitHub > Settings > Developer settings > Personal access tokens > **Fine-grained tokens** > Generate new token. Resource owner: yourself. Repository access: **Only select repositories**, pick one private test repository. Repository permissions: **Metadata: Read-only** and **Contents: Read-only**; nothing else. Short expiry (7 days).
2. Integrations > GitHub > Connect, paste the token. The connection shows your login. A wrong token is refused with "invalid key" and nothing is stored.
3. Project > an analysis > Link > GitHub. With an empty search the repositories you gave the token appear (and no others). Type `owner/repo`: the repository and its recent commits are listed.
4. Pick a commit. The link title reads `owner/repo@abc1234 <message>`. An analysis whose code repository and commit are empty now shows the repository address and the full 40-character commit; one that already had values keeps them (toast says kept).
5. Paste `https://github.com/owner/repo/commit/<40 hex>` and `https://github.com/owner/repo`: both link. A short hash address, `/tree/...`, `/blob/...`, an archive address or `raw.githubusercontent.com` is refused.
6. Push a commit to the repository, click Refresh on the repository link: "Changed since linked". The commit link does not change. Force-push the commit away (or link a commit then delete the branch it was only on, and let GitHub drop it): Refresh shows "No longer available".
7. Remove the repository from the token's access in GitHub: Refresh shows "No longer available" (GitHub answers 404). Delete the token in GitHub: the next use marks the connection expired and sends the notice.
8. Disconnect in the app: status revoked and our copy wiped. The token still exists on GitHub until you delete it there (GitHub has no API for that).
- [ ] Audit log has `integration.connected`, `external_link.created`, `analysis.updated` (source external_link), and no token.

## GitLab (manual setup, D105, D108)

Use gitlab.com with a test project, or a self-hosted server (set `INTEGRATION_ALLOWED_INSTANCE_HOSTS` if you use the allowlist).

1. GitLab > Preferences > Access tokens > Add new token, scope **read_api** only, short expiry.
2. Integrations > GitLab > Connect: server address `https://gitlab.com` (or your server), paste the token. `http://...`, an IP address, a port and a host outside the allowlist are refused.
3. Search lists your projects; typing `group/project` lists it with recent commits (subgroups work: `group/sub/project`).
4. Link a commit to an analysis: repository address and 40-character commit are filled when empty, kept when not. Paste `https://<server>/group/project/-/commit/<sha>` and the plain project address: both link; `/-/tree/...` is refused; an address on another host is refused.
5. Push, Refresh: the project link shows Changed; delete the project or revoke the token: unavailable or expired respectively.
- [ ] Network log (or the server's access log) shows only `GET /api/v4/user` and `/api/v4/projects...` calls: no repository files, archives or raw requests.

## Overleaf (link only, D105, D109)

Overleaf has no API; nothing is fetched. Use a test project.

1. In Overleaf open a project and copy the address: `https://www.overleaf.com/project/<24 hex>`.
2. In the app, Manuscript (or Document, or Files tab) > Link > Overleaf, paste it and give a title. It links; the title is yours; there is no Refresh and no status check.
3. In Overleaf > Share, turn on **link sharing** and copy the read-only link (`.../read/...`) and the edit link (`.../<digits><letters>`). Paste each: both are refused with the message to share the project in Overleaf instead; nothing is stored. Turn link sharing off again.
4. Paste the project address of a project you are not invited to: it links (we cannot check), and opening it from the app shows Overleaf's own access screen.
- [ ] Audit log and the browser address bar never contain a share token.
