# Zoom Marketplace submission: labbenchos

Everything needed to fill in the labbenchos Zoom app's publishing form at
https://marketplace.zoom.us/ (Manage, then the labbenchos app). Every answer below matches what the
code does (`backend/integrations/providers/zoom.py`, `backend/labs/video_calendar.py`,
`backend/integrations/views.py` ZoomEventsView).

## Rules for whoever fills this in

- **Already done, do not change:** OAuth redirect URL, OAuth allow list, scopes and event
  subscription. Changing the scopes breaks connecting.
- **Secrets stay hidden:** never type, copy or reveal the Client ID, Client Secret or Secret Token.
- **Character limits:** if a field is shorter than the text here, shorten the text and keep the
  meaning.
- **Owner-only fields:** a field marked **[OWNER]** needs the app owner. Leave it empty and list it
  at the end.
- **Before submitting:** stop before the final **Submit** button and let the owner review and click
  it.
- **Unsure answers:** if the form asks something not covered here, leave it and list the question
  for the owner.

## App basics

| Field | Value |
|---|---|
| App name | labbenchos |
| App type | General app, user-managed (already set) |
| Company / developer name | labbenchos |
| Developer contact name | **[OWNER]** |
| Developer contact email | achahil@ualberta.ca |
| Category | Productivity (if not offered: Collaboration) |
| Industry | Education; Research |
| Works with | Zoom Meetings |
| Pricing | Free |
| Listed on other marketplaces | No |

## Links

| Field | URL |
|---|---|
| Direct landing URL | https://labbenchos.com/settings#integrations |
| Privacy policy | https://labbenchos.com/privacy |
| Terms of use | https://labbenchos.com/terms |
| Support URL | https://labbenchos.com/zoom#support (or the email achahil@ualberta.ca if it must be an email) |
| Documentation URL | https://labbenchos.com/zoom |
| Website | https://labbenchos.com |
| OAuth redirect URL (already set) | https://labbenchos.com/api/integrations/oauth/callback/ |
| Event notification endpoint (already set) | https://labbenchos.com/api/integrations/zoom/events/ |

## Listing text

**Short description:**

> Make a Zoom meeting for any lab meeting in labbenchos, with the join link saved on the meeting.

**Long description:**

> labbenchos is a workspace for university research labs: projects, documents, tasks, a shared lab
> calendar and lab chat in one place.
>
> With the Zoom app, anyone in a lab can make a Zoom call for a lab meeting without leaving
> labbenchos. Pick "Make a Zoom call" when adding a meeting, and labbenchos creates the meeting on
> your own Zoom account, with the waiting room on, and shows its join link on the lab calendar for
> everyone in the lab. Change the meeting's title or time in labbenchos and the Zoom meeting follows;
> delete it and the Zoom meeting is deleted too. Guests you add by email get the join link from
> labbenchos.
>
> labbenchos only creates, updates and deletes the meetings it made, and reads your basic Zoom
> profile to show which account is connected. It cannot see your other meetings, recordings,
> chats or contacts. Disconnect at any time from Settings, then Integrations, or by removing the
> app in Zoom.

**How to use (if the form has a separate field):** copy the "Add the app", "Use it" and "Remove the
app" sections from https://labbenchos.com/zoom.

## Scopes: why each one is needed

| Scope | Why |
|---|---|
| `meeting:write:meeting` | Creates a scheduled Zoom meeting on the user's own account when they add a lab meeting in labbenchos and pick "Make a Zoom call". We send only the meeting title, start time, length and the settings waiting room on and join before host off. |
| `meeting:update:meeting` | When the user changes that lab meeting's title or time in labbenchos, we update the same Zoom meeting so the two stay in step. Only meetings labbenchos created are updated. |
| `meeting:delete:meeting` | When the user deletes or cancels that lab meeting in labbenchos, we delete the Zoom meeting it created so no orphaned meeting is left on their account. |
| `user:read:user` | Reads the connected user's Zoom user ID and email once, at connect time, to show which Zoom account is connected and to match the "App Deauthorized" event to the right connection. |

## Data, security and compliance answers

- **Zoom data we receive:**
  - At connect time: the user's Zoom user ID and email address.
  - For each meeting we create: its meeting ID and join URL.
- **Zoom data we store:**
  - The data received above.
  - The OAuth access and refresh tokens.
- **Where it is stored:**
  - A PostgreSQL database on a server in Canada (CanHost VPS).
  - The tokens are encrypted at rest with Fernet (AES-128-CBC with HMAC-SHA256), and the key is
    held outside the database in the server environment.
- **Data we send to Zoom:** the meeting title (up to 200 characters), start time, length, timezone
  (UTC), and the settings waiting room on and join before host off. No attendee or guest email
  addresses and no meeting notes.
- **Who sees the data:**
  - The join link is shown to members of the lab that owns the meeting. Every request is checked
    against the lab's permissions.
  - Only the person who made the meeting can change or delete it.
  - Zoom user IDs and tokens are never shown to other users.
- **Third parties:**
  - Postmark (email delivery) sends the meeting title, times and join link to guest email addresses
    the user typed in.
  - Zoom data is not sold, not used for advertising, and never passed to AI or machine-learning
    tools.
- **Encryption in transit:** HTTPS only, with TLS certificates managed by Caddy and HSTS
  (max-age one year, includeSubDomains). All calls to Zoom go over HTTPS to zoom.us and
  api.zoom.us only.
- **OAuth:**
  - Authorization code flow with PKCE (S256) and a single-use, time-limited `state` value.
  - A connection that comes back with any scope beyond the four above is refused.
- **Deauthorization:**
  - The "App Deauthorized" event is received at the event endpoint.
  - Every request's `x-zm-signature` is verified (HMAC-SHA256 with the Secret Token, constant-time
    compare) and old timestamps are rejected.
  - On a valid event we delete that user's tokens and Zoom user ID and email straight away.
- **User disconnects in labbenchos:** we call Zoom's token revoke endpoint, then delete the tokens
  and Zoom identity.
- **Retention:**
  - Tokens and Zoom identity are kept only while the user is connected.
  - A meeting's Zoom meeting ID and join link are kept with the lab meeting until the meeting is
    deleted in labbenchos.
  - Deletion requests are handled by email to the contact address and remove all Zoom data for that
    person.
- **Access control:**
  - Users sign in with email and password, with optional TOTP two-step, or Google or institution
    sign-in.
  - Staff access to the server is by SSH key only.
  - Sensitive actions, including connecting and disconnecting integrations, write audit events.
- **Logging:** tokens are never logged. Integration errors are logged without token values.
- **Backups:** none at present (the owner's choice). Data lives only on the production server.
- **Penetration test / SOC 2:** not yet. Security-sensitive changes get a separate security
  review and the full test suite before they ship.
- **Incident response:** the owners are contacted at achahil@ualberta.ca and jgogia@ualberta.ca.
  Affected users are told by email.

## Test plan for Zoom's reviewers

**Test account:** a reviewer account in a fake example lab, with two-step sign-in off.

- Email: **[OWNER: create, see below]**
- Password: **[OWNER]**

**Steps:**

1. Go to https://labbenchos.com/login, enter the email, click **Continue**, then enter the password.
2. Open **Settings**, then the **Integrations** tab. On the **Zoom** card click **Connect**, sign in
   to Zoom and click **Allow**. The card now shows the connected Zoom email.
3. Open the lab's **Calendar** and click **Add meeting**. Enter a title and a time, pick **Make a
   Zoom call** under **Video call**, and save. The meeting shows a **Join Zoom** link, and the
   meeting appears in the reviewer's Zoom account with the waiting room on.
4. Open the meeting, change its time and save. The Zoom meeting's time changes.
5. Delete the meeting. The Zoom meeting is deleted.
6. In **Settings**, then **Integrations**, click **Disconnect** on the Zoom card. Access is revoked
   at Zoom. Alternatively, remove the app at marketplace.zoom.us under Manage, then Added Apps:
   the card shows Zoom as not connected within seconds.

## Files to upload

Ready-made files are in `C:\Users\Angad\Desktop\zoom-listing\`:

- `app-icon-512.png`: the app icon (512 x 512, the green labbenchos mark on white).
- `1-integrations.png`: Settings, Integrations, with the Zoom card.
- `2-add-meeting.png`: the Add a meeting form with "Make a Zoom call".

If Zoom asks for different image sizes, resize the files and keep their content.

## Still needed from the owner

- **Third screenshot:** a meeting showing its **Join Zoom** link. Take it after connecting your own
  Zoom.
- **Demo video:** if asked, a short screen recording of the test plan above.
- **Reviewer test account:** email and password.
- **Developer contact name.**
