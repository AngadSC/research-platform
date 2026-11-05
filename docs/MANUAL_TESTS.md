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
