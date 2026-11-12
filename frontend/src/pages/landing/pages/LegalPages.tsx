import type { ReactNode } from "react";
import { Link } from "react-router";
import { CONTACT_EMAILS } from "../content";

const UPDATED = "November 12, 2026";

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
        If you sign in with Google, we receive your name, email address and Google account ID (the{" "}
        <code>openid</code>, <code>email</code> and <code>profile</code> permissions). We use them
        only to create your account and sign you in.
      </p>
      <p>If you choose to connect Google in a lab, we also ask for:</p>
      <ul>
        <li>
          <strong>Google Drive</strong> (<code>drive.file</code>): access only to the files you pick
          or that labbenchos creates, so you can link, open and edit them from your lab, and, when
          you ask, make a Google copy of a Word, Excel or PowerPoint file in your Drive. If you ask
          the AI assistant about a Drive file, we read that file with your own connection and send
          it to your AI provider (see below). We cannot see the rest of your Drive.
        </li>
        <li>
          <strong>Google Calendar and Meet</strong> (<code>calendar.events</code> and{" "}
          <code>calendar.app.created</code>): to show your events, create meetings with a Meet link
          when you ask, and keep one separate labbenchos calendar for your tasks and deadlines.
        </li>
      </ul>
      <p>
        labbenchos&rsquo;s use and transfer to any other app of information received from Google
        APIs will adhere to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy">
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. We do not sell Google user data, use it for
        advertising, or use it to train AI models. People do not read it unless you ask us to for
        support, it is needed for security, or the law requires it.
      </p>
      <p>
        You can disconnect Google at any time in labbenchos, or remove our access from your{" "}
        <a href="https://myaccount.google.com/permissions">Google account settings</a>.
      </p>

      <h2>Other connected services and AI</h2>
      <p>
        Your lab can connect other services (such as Zoom, OneDrive, Dropbox, GitHub or Zotero). We
        only connect a service when someone in your lab asks us to, and we only use it for what that
        connection is for.
      </p>
      <p>
        The AI assistant uses your own AI provider account or API key (such as Anthropic or OpenAI),
        or one your lab has set up. When you use it, the parts of your lab you ask about, including
        the contents of files you ask it to read, are sent to that provider under that
        account&rsquo;s agreement with them. Anything marked &ldquo;Contains participant data&rdquo;
        is never sent to an AI provider. If you connect an AI app such as Claude or ChatGPT to
        labbenchos, it can only see what your role in the lab allows, and you can revoke it at any
        time.
      </p>
      <p>Access tokens and API keys for connected services are stored encrypted.</p>

      <h2>Who else handles your data</h2>
      <ul>
        <li>Our hosting provider, which runs our servers in Canada.</li>
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
        data from the live system, and it leaves our backups as they expire.
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
