# Adding an integration provider

One provider is one module here plus one line in `integrations/registry.py` (`ENABLED`). The
generic UI is driven by the registry metadata, so a provider has no UI code. ARCHITECTURE
section 9 describes the framework; DECISIONS D80 to D89 record why.

## Steps

1. Create `integrations/providers/<name>.py` exporting `PROVIDER = Provider(...)` (see
   `__init__.py` for every field). `name` must equal the module name: it is stored on rows.
   `google_drive.py` is the OAuth example; `integrations/tests/fake.py` has one example per
   auth type (`FAKE`, `FAKE_KEY`, `FAKE_LINK`, `FAKE_PUBLIC`).
2. Add `"<name>",` to `registry.ENABLED`.
3. Pick the auth type:
   - `oauth2`: `scopes` (the minimum, read-only), `authorize_url`, `token_url`, `revoke_url`,
     `identity_url` and `parse_identity`. Credentials come from the environment by convention:
     `INTEGRATION_<NAME>_CLIENT_ID` / `INTEGRATION_<NAME>_CLIENT_SECRET` (no settings change).
     The redirect URI to register is `FRONTEND_URL/api/integrations/oauth/callback/`.
   - `api_key`: `connect_fields` (labels and help text for `api_key`, optional `secret`, and
     `instance_url` when `needs_instance_url`), plus `identity_url`/`parse_identity` or an
     `identify(account)` hook: one cheap call that proves the key works. `sign(kwargs, key,
     secret)` puts the key on a request (default: a bearer header; REDCap puts `token` in the
     form body). A 401 means "this key is dead" and expires the account, so a provider that
     answers 401 for "no access to this item" must map that itself before returning.
   - `link_only` (no API, e.g. Overleaf): `url_pattern`, `link_hosts`, `link_methods =
     ("paste_url",)`. The person's own title is stored. `fetch_item` is optional.
   - `public` (no credentials, e.g. a public Zenodo record): `api_hosts`, `fetch_item(None, id)`.
4. Metadata for the UI: `category`, `icon` (a key, not a URL), `link_targets` (where a link may
   hang: `project` is the Files tab), `link_methods` (`picker`, `search`, `paste_url`),
   `external_id_pattern` (as tight as the provider's real ids), `url_pattern` (a regex with an
   `id` group, fullmatched against a pasted address), `link_hosts`.
5. Hooks (all optional except `fetch_item` for every type but link_only):
   - `fetch_item(account, external_id) -> dict | None` with `title`, `url`, `mime_type`,
     `modified_at` (datetime), `version`, `checksum`; `None` when the item is gone.
   - `search_items(account, query, target_kind) -> [dict]` with `id`, `title`, `subtitle`,
     `modified`, `url` (20 kept). `query` may be empty: return recent items or `[]`.
   - `apply_to_target(target_kind, meta) -> {field: value}`: values for the linked record, e.g.
     an analysis' `code_repo_url` and `code_commit`. Written only into empty fields and only if
     the field's validators accept them (D76, D86).
6. Tests: `integrations/tests/test_<name>.py` with a `ProviderContract` subclass (see
   `integrations/tests/provider_contract.py` and `test_fake_contract.py`): the provider, an item
   id, its pasted URL, its title, the target, and the mocked replies per stage (`identity`,
   `item`, `item_changed`, `item_gone`, `search`). Add provider-specific tests beside it.
   Run `docker compose run --rm -e TEST_DB_NAME=test_<you> backend pytest -q integrations`.

## Security checklist (every item is a review blocker)

- [ ] **Metadata only** (D64, D84). Never request file contents, exports, archives, raw blobs,
      survey responses or REDCap records. `metadata_only` stays `True`; `test_registry.py` scans
      the module's string literals for download paths (`CONTENT_PATHS` in
      `provider_contract.py`). Extend that list if your API spells downloads differently. REDCap:
      only `content=project`/`metadata`-style calls. protocols.io: request metadata fields only.
- [ ] **Least scope**: read-only scopes; no identity scopes unless the identity call needs them.
- [ ] **All HTTP through `integrations.http.send`** with `provider=PROVIDER` and the `account`
      (or `None` for public). Never `requests` directly, never a second session: `send` enforces
      https, port 443, the host allowlist, same-host redirects, the SSRF address checks, DNS
      pinning, timeouts and retries (D67, D82).
- [ ] **`api_hosts` is exact**: only the API hosts credentials may go to. Self-hosted providers
      leave it empty and rely on the account's instance host.
- [ ] **Quote ids** you put in a URL: `urllib.parse.quote(external_id, safe="")`, and keep
      `external_id_pattern` tight (D75).
- [ ] **No secrets in errors or logs**: raise `IntegrationError` with a fixed message; never
      include a response body, header, query string or token. Decorate any function that
      holds a token in a local with `@sensitive_variables`.
- [ ] **Treat responses as untrusted**: catch `KeyError`/`ValueError`/`TypeError` while
      parsing and raise `IntegrationError`; return web links only on `link_hosts` (the
      framework blanks others).
- [ ] **`link_hosts` pinned** for any provider with `paste_url`, https only (D78).
- [ ] **Contract tests pass** (connect, search, fetch, link, changed, gone, revoke, no secrets
      leaked) and every new decision is recorded in your DECISIONS range.
