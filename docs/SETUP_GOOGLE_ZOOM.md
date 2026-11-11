# Turning on Google and Zoom for everyone

Google (Drive, Calendar and Meet) and Zoom show a dimmed **Connect** button until the site has
its **app details**. This is a one-time job for whoever runs the site. Once it is done, **every
member of every lab connects their own account with one click**, and nobody touches server
settings again.

Why it can't be skipped: Google and Zoom only let an app talk to people's accounts if the app is
registered with them. Registering gives the site a **client ID** and **client secret**, which go
in the server's settings. Everyone's own sign-in then happens on Google's and Zoom's pages, with
their own passwords, and the site never sees those.

You do this once per service, not once per lab or per person.

| You need | For | Goes in |
|---|---|---|
| Google client ID and secret | Drive, Calendar and Meet (one sign-in, D262) | `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET` |
| Google Picker key and project number | The "From Drive" file picker | `GOOGLE_DRIVE_API_KEY`, `GOOGLE_DRIVE_APP_ID` |
| Zoom client ID and secret | Making Zoom meetings | `INTEGRATION_ZOOM_CLIENT_ID`, `INTEGRATION_ZOOM_CLIENT_SECRET` |

The **redirect address** you register with both is your site's address plus
`/api/integrations/oauth/callback/`:

- Your live site: `https://labbenchos.com/api/integrations/oauth/callback/`
- On your own computer: `http://localhost:5173/api/integrations/oauth/callback/`

It must match exactly, including the trailing slash.

---

## 1. Google (Drive, Calendar and Meet)

The live site already has a Google Cloud project with a Drive client (see `DEPLOY.md`). If you
are using that one, you only need steps 2, 3 and 4. Skip 1 and 5.

Google's console moves things around now and then. If a menu name here has changed, search the
console for the name in bold.

1. **Create a project** at <https://console.cloud.google.com/> (skip if you have one).
2. **Turn on three APIs** (search "API Library"): **Google Drive API**, **Google Picker API** and
   **Google Calendar API**. Meet needs nothing extra: its links are made through Calendar.
3. **Set up the consent screen** (**APIs & Services**, then **OAuth consent screen**, also called
   **Google Auth platform**):
   - User type **External**.
   - App name, your support email, and your site's address and privacy policy address.
   - **Authorized domains**: your site's domain, for example `labbenchos.com`.
   - **Scopes**: add exactly these three and nothing wider:
     - `https://www.googleapis.com/auth/drive.file`
     - `https://www.googleapis.com/auth/calendar.events`
     - `https://www.googleapis.com/auth/calendar.app.created`
4. **Make or check the sign-in client** (**Credentials**, then **Create credentials**, then
   **OAuth client ID**, type **Web application**):
   - **Authorized redirect URI**: the redirect address above.
   - Copy the **client ID** and **client secret** into `GOOGLE_DRIVE_CLIENT_ID` and
     `GOOGLE_DRIVE_CLIENT_SECRET`.
   - This one client serves Drive, Calendar and Meet together. There is no separate Calendar
     client.
5. **Picker key and project number** (for "From Drive"):
   - **Credentials**, then **Create credentials**, then **API key**. Restrict it to **HTTP
     referrers** (your site's address) and to the **Google Picker API**. Put it in
     `GOOGLE_DRIVE_API_KEY`.
   - The **project number** is on the project's **Dashboard**, a long number. Put it in
     `GOOGLE_DRIVE_APP_ID`.

### Letting anyone connect (Google)

A new Google app starts in **Testing**. In Testing, only people you list as **test users** (up to
100) can connect, and their connection stops working after 7 days. To let anyone connect:

1. On the consent screen, click **Publish app** to move it to **In production**.
2. Google then asks you to **verify** the app, because the Calendar permissions are classed as
   **sensitive**. Until it is verified:
   - Anyone can connect, but each person sees an "unverified app" warning first.
   - The app is limited to **100 people** in total.
3. To verify, Google asks for: a working site on your own verified domain, a privacy policy
   page, the reason you need each permission, and a short screen recording of the sign-in and of
   each permission being used. It can take days to weeks. Start it early.

`drive.file` alone does not need this verification, so a site that only used Drive could skip it.
The Calendar permissions are what trigger it.

---

## 2. Zoom

1. Go to <https://marketplace.zoom.us/> and sign in with the Zoom account that will own the app.
2. **Develop**, then **Build App**, then **General App**. Choose **User-managed** (each person
   authorizes their own account), not account-level.
3. **OAuth information**:
   - **OAuth redirect URL** and **OAuth allow list**: the redirect address above (add your
     localhost one too if you test locally).
   - Copy the **client ID** and **client secret** into `INTEGRATION_ZOOM_CLIENT_ID` and
     `INTEGRATION_ZOOM_CLIENT_SECRET`.
4. **Scopes**: add exactly these four and nothing more:
   - `meeting:write:meeting`
   - `meeting:update:meeting`
   - `meeting:delete:meeting`
   - `user:read:user`

   Zoom grants whatever the app was set up with. If the app has extra scopes, connecting fails
   on purpose ("The service granted more access than we asked for"), so keep it to these four.
5. Fill in the basic information Zoom asks for (app name, description, support contact, privacy
   policy and terms addresses).

### Letting anyone connect (Zoom)

Until Zoom approves the app, only people in **your own Zoom account** can authorize it. To let
anyone connect, **submit the app for publishing** in the Marketplace. Zoom reviews it, and may
ask for a short demo and for you to explain each scope. Zoom's requirements change, so check
what its Marketplace asks for when you submit.

---

## 3. Put the details in the server's settings

**On your own computer**, create a file named `.env` in the project folder (next to
`docker-compose.yml`), with only the lines you have:

```bash
GOOGLE_DRIVE_CLIENT_ID=your-google-client-id
GOOGLE_DRIVE_CLIENT_SECRET=your-google-client-secret
GOOGLE_DRIVE_API_KEY=your-picker-key
GOOGLE_DRIVE_APP_ID=your-project-number
INTEGRATION_ZOOM_CLIENT_ID=your-zoom-client-id
INTEGRATION_ZOOM_CLIENT_SECRET=your-zoom-client-secret
```

Never commit `.env`. Then restart so the server reads it:

```bash
docker compose up -d --force-recreate backend worker beat
```

**On the live site**, put the same lines in `~/app/deploy/.env.prod` on the server (see
`DEPLOY.md`, section 2), then:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker beat
```

## 4. Check it worked

1. Open **Integrations** in a lab. The **Google** card and the **Zoom** card should now have a
   normal **Connect** button, not a dimmed one with "Not set up on this server".
2. Click **Connect** on Google. Google's consent screen should list Drive, Calendar and Meet
   permissions together. Allow all of them. You land back on Integrations with the card showing
   your email and **Active**.
3. Open **Calendar**, then **Add meeting**, and choose **Make a Google Meet call**. Save. The
   join link should fill in by itself.
4. Do the same with **Make a Zoom call**.

If you are told **"Allow every requested permission to connect"**, the person unticked a box on
Google's screen. They need to connect again and allow everything.

## What people see if it is not set up

- A dimmed **Connect** button with "Not set up on this server", and a line on the page explaining
  that whoever runs the site has to finish a one-time setup first.
- On the meeting form, the Google Meet and Zoom choices are greyed out with the same note.

Nothing breaks. The `.ics` link (Calendar, then Subscribe) and pasting a meeting link work
without any of this.
