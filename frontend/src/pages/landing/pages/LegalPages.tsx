import type { ReactNode } from "react";
import { Link } from "react-router";
import { CONTACT_EMAILS } from "../content";

const UPDATED = "November 18, 2026";

function Contact() {
  return (
    <>
      {CONTACT_EMAILS.map((email, i) => (
        <span key={email}>
          {i > 0 && " or "}
          <a href={`mailto:${email}`}>{email}</a>
        </span>
      ))}
    </>
  );
}

function Legal({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="lb-wrap lb-section lbp-legal">
      <h1 className="lb-h2">{title}</h1>
      <p className="lbp-legal-updated">Last updated {UPDATED}</p>
      {children}
    </article>
  );
}

export function PrivacyPage() {
  return (
    <Legal title="Privacy policy">
      <p>
        labbenchos (&ldquo;we&rdquo;, &ldquo;us&rdquo;) is a workspace for research labs. This
        policy says what we collect when you use labbenchos.com, why, who it goes to, and what you
        can do about it.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>
          <strong>Your account:</strong> your email address, name, and, if you add them, your
          pronouns, bio and profile picture. If you sign up with a password, we store only a secure
          hash of it.
        </li>
        <li>
          <strong>What you put in a lab:</strong> projects, tasks, documents, files, datasets,
          messages, papers and the other records you and your lab create. Your lab owns this
          content.
        </li>
        <li>
          <strong>Security records:</strong> when you sign in and when important things change, we
          keep an audit log entry with the time, the action and your browser&rsquo;s user agent. We
          do not store IP addresses. We use yours only for a short time to limit repeated sign-in
          attempts, and then it is forgotten.
        </li>
        <li>
          <strong>Cookies:</strong> we use only the cookies needed to keep you signed in and to
          protect forms. We do not use advertising or tracking cookies, and we do not use analytics
          services.
        </li>
      </ul>

      <h2>Google sign-in and Google services</h2>
      <p>
        Each person connects their own Google account, in a lab&rsquo;s Integrations settings, and
        chooses which services to connect: Drive, Calendar and Meet, or Google Chat. This section
        covers everything labbenchos does with data from Google.
      </p>

      <h3>Signing in with Google</h3>
      <p>
        If you sign in with Google, we receive your name, email address and Google account ID (the{" "}
        <code>openid</code>, <code>email</code> and <code>profile</code> permissions). We use them
        only to create your account and sign you in. Signing in does not give us access to anything
        else in your Google account.
      </p>

      <h3>Google Drive</h3>
      <ul>
        <li>
          <strong>Permission:</strong> <code>drive.file</code>. We can reach only the files you pick
          in Google&rsquo;s file picker and the files labbenchos creates for you. We cannot see the
          rest of your Drive.
        </li>
        <li>
          <strong>Linking a file:</strong> we store its title, type, link and version. Everyone who
          can see the project sees the title and the link. Opening the file still needs their own
          access in Google. When you link a file to a project, we ask whether it identifies
          participants.
        </li>
        <li>
          <strong>Daily check:</strong> once a day, for files linked to a project as links, we use
          the connection of the person who linked each one to read its title, version and
          last-modified time, to tell the project when it changes or disappears. In a
          project&rsquo;s participant tracker, &ldquo;Check links now&rdquo; reads a linked Drive
          file&rsquo;s title, type and last-modified time when someone asks for it, using their own
          connection. Neither check reads what is in the file.
        </li>
        <li>
          <strong>Copies in your Drive:</strong> &ldquo;Edit in Google&rdquo; uploads a copy of a
          Word, Excel or PowerPoint file from the project to your own Drive as a Google Doc, Sheet
          or Slides file. &ldquo;Send to Google Sheets&rdquo; and &ldquo;Send picture to Google
          Drive&rdquo; on statistics results put a copy of that result in your Drive. These copies
          are yours.
        </li>
        <li>
          <strong>The AI assistant:</strong> it reads a Drive file&rsquo;s contents only when you
          ask it to, using your own connection, and sends them to your AI provider (see below) to
          answer you. The same applies when you use labbenchos from an AI app such as Claude or
          ChatGPT (an MCP connector): the contents go to that app. If you ask Claude to analyse a
          Drive file with code, a copy of the file goes to Anthropic&rsquo;s code sandbox, under
          your or your lab&rsquo;s Anthropic account (see below).
        </li>
        <li>
          <strong>Participant data:</strong> a file or folder marked &ldquo;Identifies
          participants&rdquo; is never read for, or given to, any AI tool.
        </li>
        <li>
          <strong>After you disconnect:</strong> files you linked stay linked in their projects, as
          project records: their title, type, link and version details. The daily check for them
          stops until you connect again. Copies in your Drive stay there.
        </li>
      </ul>

      <h3>Google Calendar and Meet</h3>
      <ul>
        <li>
          <strong>Permissions:</strong> <code>calendar.events</code> to add, change and remove
          meetings on your main calendar, to show you your own events and to send your answer to an
          invitation, and <code>calendar.app.created</code> to manage one separate calendar that
          labbenchos creates. We also receive your email address (<code>openid</code>,{" "}
          <code>email</code>) to know which Google account you connected.
        </li>
        <li>
          <strong>Meetings:</strong> when you schedule a lab meeting with a Google Meet call, we
          create the event on your primary calendar with its title, times and the email addresses of
          the lab members you invite as guests, plus any other email addresses you type in as
          guests. When you add guests by email, Google emails them the invitation with the Meet
          link. We store the event&rsquo;s ID, its Meet link and the guests&rsquo; email addresses
          (only you and the people on the meeting see them), and update or delete the event when you
          change or cancel the meeting here.
        </li>
        <li>
          <strong>Your own events:</strong> when you open the labbenchos calendar, we read your
          primary calendar&rsquo;s events for the dates shown, so you can see them next to your
          lab&rsquo;s, with who is invited and how they answered. Only you see them, we do not store
          them, and you can turn this off. If you accept, decline or answer &ldquo;maybe&rdquo; to
          an invitation here, we change only your own answer on that event, and Google tells its
          organiser.
        </li>
        <li>
          <strong>The labbenchos calendar (optional):</strong> it is off until you turn it on. Then
          we create a calendar named &ldquo;labbenchos: <em>your lab</em>&rdquo; in your account and
          keep your meetings, your tasks with due dates and your projects&rsquo; deadlines on it
          (titles, times, the project name and any join link), updated about every 15 minutes.
        </li>
        <li>
          <strong>After you disconnect:</strong> we stop reading and changing your calendar, and we
          delete your calendar settings and our list of what we put on the labbenchos calendar.
        </li>
        <li>
          <strong>The labbenchos calendar after you disconnect:</strong> when you disconnect, you
          can tick &ldquo;Also delete the labbenchos calendar from your Google Calendar&rdquo;. We
          then delete that calendar and its events from your Google account, before we remove our
          access. We touch nothing else in your Google account. If you don&rsquo;t tick it, or your
          connection is removed another way (for example, you leave the lab), the calendar stays in
          your Google Calendar until you delete it there: in Google Calendar, open the
          calendar&rsquo;s &ldquo;Settings and sharing&rdquo; and choose &ldquo;Remove
          calendar&rdquo;.
        </li>
        <li>
          <strong>Meetings after you disconnect:</strong> Meet meetings you created stay on your
          primary calendar, and on your guests&rsquo; calendars, until deleted in Google. In
          labbenchos the meeting keeps its Meet link and the Google event ID, as a lab record, but
          changes to it are no longer sent to Google.
        </li>
      </ul>

      <h3>Google Chat</h3>
      <ul>
        <li>
          <strong>Permissions:</strong> see which conversations (spaces, group chats and direct
          messages) you are in (<code>chat.spaces.readonly</code>); read, post and delete messages,
          deleting only messages labbenchos posted (<code>chat.messages</code>); and, if you allow
          them, see who is in a conversation (<code>chat.memberships.readonly</code>) and look up
          names and photos in your organisation&rsquo;s Google directory (
          <code>directory.readonly</code>). We also receive your Google account ID and email address
          (<code>openid</code>, <code>email</code>) to recognise your own messages.
        </li>
        <li>
          <strong>Syncing a chat:</strong> a PI or lab administrator can link the lab chat, and a
          project lead a project&rsquo;s chat, to one Google Chat conversation they are in. We then
          read new messages in that conversation about every 15 seconds, using their connection, and
          store each message&rsquo;s text, time and sender. Attachments are not copied, and messages
          from apps and bots are skipped.
        </li>
        <li>
          <strong>Posting:</strong> messages written in a synced chat are posted to the
          conversation. If you have connected Google Chat and are in the conversation, they are
          posted as you. Otherwise they are posted through the connection of the person who linked
          it, starting with your name and email address and followed by &ldquo;via
          labbenchos&rdquo;. Anyone in the conversation, including people outside your lab, can see
          them.
        </li>
        <li>
          <strong>Deleting:</strong> when a message we posted is deleted in labbenchos, we delete it
          in Google Chat too. A message deleted in Google Chat stays in labbenchos until its author,
          a lab administrator or the project lead removes it here.
        </li>
        <li>
          <strong>Importing:</strong> whoever may link a chat can also copy one thread, or a
          conversation&rsquo;s latest messages (up to 1000), into it, read with their own
          connection. Nothing is sent back to Google.
        </li>
        <li>
          <strong>Names and photos:</strong> a sender who has connected Google Chat in the lab
          appears as that lab member. Anyone else who wrote in the conversation, including people
          outside the lab, appears with their name and a link to their profile photo, taken from
          your organisation&rsquo;s directory or from the conversation and saved with the message.
          Directory lookups are kept for a day. When a conversation is linked we also read who is in
          it (if that permission was allowed), so people can @mention them, and the emoji reactions
          on recent messages with the names of the people who reacted, so they show here. Recent
          messages&rsquo; reactions are re-read every few minutes.
        </li>
        <li>
          <strong>Who sees it:</strong> messages synced or imported into the lab chat are visible to
          everyone in the lab; in a project&rsquo;s chat, to everyone who can see the project.
          Everyone in that chat also sees the name of the linked conversation.
        </li>
        <li>
          <strong>After a chat is unlinked:</strong> we stop reading and posting at once and delete
          the link. Messages already copied in stay in the chat, with their senders&rsquo; names and
          photo links, as part of its history, until they are deleted in labbenchos.
        </li>
        <li>
          <strong>If the person who linked it disconnects</strong> Google Chat, removes our access
          in their Google account, or leaves the lab, the link pauses: nothing is read or posted,
          and the messages that came in through their connection are hidden from everyone in
          labbenchos. If they connect the same Google account again, the link resumes and those
          messages show again. Meanwhile the copies stay stored, hidden, until you ask us to delete
          them (see below). Imported messages are hidden in the same way while the connection of the
          person who imported them is off. We check every hour whether access was removed in Google.
          Messages posted in Google Chat stay there.
        </li>
        <li>Google Chat messages are never given to the AI assistant or to AI apps.</li>
      </ul>

      <h3>How we use Google data</h3>
      <p>
        labbenchos&rsquo;s use and transfer to any other app of information received from Google
        APIs will adhere to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy">
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. We use Google data only to provide the features
        described above, and send it to an AI provider only to answer a request you make. We do not
        sell it or use it for advertising. We do not use Google Workspace data to develop, improve
        or train generalized artificial intelligence or machine-learning models. People do not read
        it unless you ask us to for support, it is needed for security, or the law requires it.
      </p>

      <h3>Keeping and deleting Google data</h3>
      <ul>
        <li>
          <strong>Tokens:</strong> access tokens are stored encrypted. When you disconnect, a lab
          administrator removes your connection, you leave a lab or your account is closed, we
          delete them and revoke our access at Google. If the same Google account is still connected
          elsewhere in labbenchos, we revoke it when the last of those connections goes.
        </li>
        <li>
          <strong>What we keep about a removed connection:</strong> the service, its status and when
          it was connected and last used. We delete the Google email address, the permissions you
          granted, and Google&rsquo;s ID for the account; in its place we keep a scrambled code that
          only matches when you connect the same Google account again, so your links and meetings
          reconnect to it. Your calendar settings are deleted (see Google Calendar above).
        </li>
        <li>
          <strong>Lab records stay:</strong> what was already saved as lab content stays until it is
          deleted in labbenchos or the lab is deleted: linked files&rsquo; titles, links and
          versions, meetings with their Meet links, and synced or imported Chat messages with their
          senders&rsquo; names and photo links. What labbenchos put in your Google account (copies
          in Drive, calendar events, posted messages) stays there until you delete it, except the
          labbenchos calendar if you ask us to delete it.
        </li>
        <li>
          <strong>The audit log</strong> keeps its entries about connecting and disconnecting,
          including the Google email address shown when you connected. These are security records
          and are not changed afterwards.
        </li>
        <li>
          You can disconnect at any time in Integrations, or remove our access from your{" "}
          <a href="https://myaccount.google.com/permissions">Google account settings</a>. If you
          remove it in Google, the connection shows here as needing to reconnect and our tokens are
          wiped, but the details described above stay until you disconnect it, or the lab removes
          it, which deletes them.
        </li>
      </ul>

      <h3>Asking us to delete your Google data</h3>
      <p>
        Email <Contact /> from your account&rsquo;s address and say which Google account it is
        about. We will then, in every lab (or only the labs you name):
      </p>
      <ul>
        <li>
          remove every connection you have, deleting the tokens and revoking our access at Google
          (unless that Google account is still connected by someone else in labbenchos). We only
          change connections made by your own labbenchos account: one that someone else made with
          the same Google address is not touched;
        </li>
        <li>
          delete the Google email address, permissions and account ID we hold for those connections,
          leaving no code that could match them again (the audit log entries described above are
          kept as security records);
        </li>
        <li>delete your calendar settings and our list of what we put on your calendar;</li>
        <li>
          remove links to Google Chat conversations made with your connection, and delete the
          messages that were copied in or imported through it;
        </li>
        <li>
          remove your Google profile photo link from chat messages linked to your labbenchos
          account. Directory lookups of your name expire within a day.
        </li>
      </ul>
      <p>
        Messages copied in from a Google Chat conversation without a link to your labbenchos account
        are stored under the name they appear under. Whether or not you have an account, tell us
        that name and the lab, and we will delete the messages stored under that name in that lab.
        Lab records, such as linked files&rsquo; titles and links, meetings, and messages you wrote
        in labbenchos, belong to the lab: ask its administrators about them. If a lab still has a
        conversation linked, what you write there later is copied in again; leave the conversation
        or ask the lab to unlink it to stop that.
      </p>

      <h2>Zoom</h2>
      <p>
        Each person connects their own Zoom account, in a lab&rsquo;s Integrations settings, so they
        can make Zoom calls for lab meetings.
      </p>
      <ul>
        <li>
          <strong>What we send to Zoom:</strong> when you schedule a lab meeting with a Zoom call,
          we create a Zoom meeting on your account with the meeting title, start time and length,
          with the waiting room on. We update or delete it when you change or cancel the meeting
          here. We never send Zoom meeting notes, or the email address of any attendee or guest.
        </li>
        <li>
          <strong>What we store:</strong> your Zoom user ID and email address, your access tokens
          (encrypted), and, for each meeting, its Zoom meeting ID and join link. Permissions: we can
          create, change and delete meetings on your account and read your basic profile. We cannot
          see your other meetings, recordings or contacts.
        </li>
        <li>
          <strong>Guests:</strong> Zoom sends no invitations for these meetings. If you type guest
          email addresses into a Zoom meeting, labbenchos emails each guest the meeting title, times
          and join link, and emails them again if the title or time changes or the meeting is
          cancelled. We store those addresses with the meeting (only you and the people on it see
          them).
        </li>
        <li>
          <strong>If you disconnect:</strong> we revoke our access at Zoom and delete your tokens
          and your Zoom user ID and email address. Meetings already made stay in the lab with their
          join link, and stay in your Zoom account until you delete them there. We can no longer
          change them from labbenchos. If you remove the labbenchos app in Zoom, Zoom tells us and
          we do the same.
        </li>
      </ul>

      <h2>Other connected services and AI</h2>
      <p>
        Your lab can connect other services (such as OneDrive, Dropbox, GitHub or Zotero). We only
        connect a service when someone in your lab asks us to, and we only use it for what that
        connection is for.
      </p>
      <p>
        The AI assistant uses your own AI provider account or API key (such as Anthropic or OpenAI),
        or one your lab has set up. When you use it, the parts of your lab you ask about, including
        the contents of files you ask it to read, are sent to that provider under that
        account&rsquo;s agreement with them. Anything marked &ldquo;Identifies participants&rdquo;
        is never sent to an AI provider. If you ask Claude to analyse files, copies of them go to
        Anthropic&rsquo;s code sandbox, which Anthropic keeps for up to 30 days. Files the code
        makes are deleted from that account once saved to your project; any not saved can stay there
        until the account&rsquo;s owner deletes them. If your lab runs its own analysis server,
        files you ask to analyse there are copied to it for the run and removed afterwards. If you
        connect an AI app such as Claude or ChatGPT to labbenchos, it can only see what your role in
        the lab allows, and you can revoke it at any time.
      </p>
      <p>Access tokens and API keys for connected services are stored encrypted.</p>

      <h2>Who else handles your data</h2>
      <ul>
        <li>
          Our hosting provider, which runs our one server in Canada. Your account, lab content and
          everything else are stored in our database on that server, and uploaded files on its disk.
          We do not use a separate cloud file store.
        </li>
        <li>Postmark, which sends our emails (sign-up confirmations, invitations, notices).</li>
        <li>Services you or your lab choose to connect, as described above.</li>
      </ul>
      <p>
        We do not sell personal information. We share it with others only as listed here, or when
        the law requires it.
      </p>

      <h2>How long we keep it</h2>
      <p>
        We keep your account while it is open. Lab content is kept for as long as the lab keeps it,
        under the lab&rsquo;s retention settings. When an account or lab is deleted, we delete its
        data from the live database and file store.{" "}
        {/* Owner confirmed (18 Nov 2026): no backups, by choice. If backups are added, state their
        retention here before they start. */}
        We do not make backups, so data deleted from the live database and file store is gone. If we
        add backups, we will update this policy to say how long they are kept first.
      </p>

      <h2>Your choices</h2>
      <p>
        You can see and change your profile in your account settings, and disconnect any service at
        any time. To get a copy of your data, correct it, or delete your account, contact us at{" "}
        <Contact />. If you are in a lab, some content belongs to the lab, and the lab&rsquo;s
        administrators decide what happens to it.
      </p>

      <h2>Changes</h2>
      <p>
        If we change this policy, we will update the date above, and tell you in the app if the
        change is significant.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about privacy: <Contact />. See also our <Link to="/terms">terms of service</Link>
        .
      </p>
    </Legal>
  );
}

export function TermsPage() {
  return (
    <Legal title="Terms of service">
      <p>
        These terms apply when you use labbenchos.com. By creating an account or using the site, you
        agree to them.
      </p>

      <h2>Your account</h2>
      <p>
        Keep your sign-in details safe and give accurate information. You are responsible for what
        happens under your account. Tell us at <Contact /> if you think someone else has used it.
      </p>

      <h2>Your content</h2>
      <p>
        You and your lab own what you put into labbenchos. You give us permission to store, process
        and show it only so we can run the service for you. Make sure you have the right to upload
        it, and follow your institution&rsquo;s rules and any ethics approvals that apply to your
        research data.
      </p>

      <h2>Acceptable use</h2>
      <p>Do not use labbenchos to:</p>
      <ul>
        <li>break the law or anyone&rsquo;s rights, including privacy and copyright;</li>
        <li>get into accounts, labs or data you have not been given access to;</li>
        <li>upload malware, or disrupt or overload the service;</li>
        <li>send spam or abusive messages.</li>
      </ul>

      <h2>Connected services and AI</h2>
      <p>
        When you connect another service (such as Google, Zoom or an AI provider), your use of it is
        also governed by that service&rsquo;s own terms. AI answers can be wrong; check them before
        you rely on them. Any AI usage is billed by your AI provider, not by us.
      </p>

      <h2>The service</h2>
      <p>
        labbenchos is under active development. We work to keep it available and your data safe, but
        we provide it &ldquo;as is&rdquo;, without warranties, and features may change. Keep your
        own copies of anything you cannot afford to lose.
      </p>

      <h2>Liability</h2>
      <p>
        To the extent the law allows, we are not liable for indirect or consequential losses, or for
        loss of data or profits, arising from your use of labbenchos.
      </p>

      <h2>Ending your use</h2>
      <p>
        You can stop using labbenchos at any time and ask us to delete your account. We may suspend
        an account that breaks these terms or puts other users at risk.
      </p>

      <h2>Changes and law</h2>
      <p>
        We may update these terms. If a change is significant, we will tell you in the app. These
        terms are governed by the laws of Alberta and the federal laws of Canada that apply there.
      </p>

      <h2>Contact</h2>
      <p>
        Questions: <Contact />. See also our <Link to="/privacy">privacy policy</Link>.
      </p>
    </Legal>
  );
}
