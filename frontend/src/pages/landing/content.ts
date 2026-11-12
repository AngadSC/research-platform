/** Copy for the public home page, kept apart from the layout so it is easy to edit. */

/** Where every "Contact us" button goes: the contact block at the bottom of the pricing page. */
export const CONTACT_PATH = "/pricing#contact";
/** Address shown in that block. Fill in before launch; the page shows a placeholder until then. */
export const CONTACT_EMAILS = ["achahil@ualberta.ca", "jgogia@ualberta.ca"];

export const STEPS = [
  {
    label: "Plan",
    title: "Plan the project",
    body: "Turn an idea into a structured project with goals, a timeline and the right people from day one.",
    points: [
      {
        t: "Project templates",
        d: "Start from templates for common study types, or build your own.",
      },
      { t: "Timelines and milestones", d: "Map out the study and share it with the whole team." },
      { t: "Literature and notes", d: "Keep background reading and references with the project." },
      {
        t: "AI planning help",
        d: "Ask your AI to outline aims or draft a study plan from your notes.",
      },
    ],
  },
  {
    label: "Ethics",
    title: "Get ethics approval",
    body: "Keep every ethics application, approval and amendment organized and linked to the work it covers.",
    points: [
      { t: "Application tracker", d: "Track each submission from draft to approval." },
      { t: "Consent form templates", d: "Versioned consent forms tied to the right protocol." },
      { t: "Amendments and renewals", d: "Full history plus reminders before approvals expire." },
      {
        t: "Linked approvals",
        d: "Attach approval numbers to projects so nothing runs without one.",
      },
    ],
  },
  {
    label: "Funding",
    title: "Secure and manage funding",
    body: "Track grants from application to final report, and see what every dollar is going toward.",
    points: [
      { t: "Grant deadline tracker", d: "Never miss an application or reporting date." },
      { t: "Budgets by grant", d: "Link purchases and inventory to the grant that paid for them." },
      { t: "Reporting made easy", d: "Pull progress and spending together when reports are due." },
      { t: "AI drafting", d: "Draft grant sections from your existing project notes." },
    ],
  },
  {
    label: "Team & training",
    title: "Build and train the team",
    body: "Bring people on board quickly and keep everyone certified for the work they do.",
    points: [
      { t: "Invite by email", d: "New members join the right lab with the right role in seconds." },
      { t: "Onboarding checklists", d: "A starter list of protocols and training for each role." },
      { t: "Training records", d: "Certificates on file with reminders before they lapse." },
      { t: "Roles and permissions", d: "Everyone sees exactly what they need, nothing more." },
    ],
  },
  {
    label: "Run experiments",
    title: "Run the research",
    body: "Everything you need at the bench or in the testing room, in one place.",
    points: [
      { t: "Lab notebook", d: "Record entries linked to protocols, samples and people." },
      { t: "Protocols and SOPs", d: "Always the latest version, with full history." },
      {
        t: "Inventory and orders",
        d: "Check stock, find locations and track orders until they arrive.",
      },
      { t: "Tasks and calendar", d: "Tasks, deadlines and lab events on one shared calendar." },
    ],
  },
  {
    label: "Analyze",
    title: "Analyze your data",
    body: "Keep data organized, connected to its source, and easy to explore with the AI you choose.",
    points: [
      { t: "Linked data files", d: "Connect datasets from Google Drive and other storage." },
      { t: "Version tracking", d: "Know which data and protocol produced each result." },
      { t: "Ask your AI", d: "Query your notes, protocols and data in plain language." },
      {
        t: "Shared analysis notes",
        d: "Discuss results with the team right where the data lives.",
      },
    ],
  },
  {
    label: "Publish & share",
    title: "Publish and pass it on",
    body: "Write up, share results and make sure the knowledge stays with the lab after people move on.",
    points: [
      { t: "Drafts and authorship", d: "Collaborate on manuscripts and track contributions." },
      { t: "References", d: "Pull citations from your reference manager." },
      { t: "Conference materials", d: "Keep posters and talks with the project they came from." },
      { t: "Archive and handoff", d: "Finished projects stay searchable for future members." },
    ],
  },
];

export const ROLES = [
  {
    id: "pi",
    label: "PIs & lab heads",
    title: "Oversight without the chasing",
    body: "See progress across every project and person, and know your lab is compliant before anyone asks.",
    points: [
      "Lab-wide view of projects, ethics and funding",
      "Training compliance at a glance",
      "Continuity when students graduate",
    ],
  },
  {
    id: "mgr",
    label: "Lab managers",
    title: "Keep the lab running smoothly",
    body: "Inventory, equipment and onboarding in one place instead of five spreadsheets.",
    points: [
      "Inventory, orders and the lab calendar",
      "Onboarding checklists for new members",
      "Roles and permissions by lab",
    ],
  },
  {
    id: "stu",
    label: "Students & RAs",
    title: "Know exactly what to do next",
    body: "Find the right protocol, see your tasks and track your training from your first day.",
    points: [
      "Clear task lists for each project",
      "Always-current protocols",
      "Your training status in one place",
    ],
  },
];

export const PLANS = [
  {
    name: "Individual",
    desc: "For a single researcher, student or independent project.",
    featured: false,
    features: [
      "Projects, tasks and documents",
      "Datasets, analyses and lineage",
      "Connect Drive, GitHub, Zotero and more",
      "Bring your own AI",
      "Email support",
    ],
  },
  {
    name: "Lab",
    desc: "For a research group working together under one PI.",
    featured: true,
    features: [
      "Everything in Individual",
      "Invite your whole lab by email",
      "Ethics, funding and data plans",
      "Training records, inventory and orders",
      "Handover reports when people leave",
    ],
  },
  {
    name: "Institution",
    desc: "For departments, faculties and research institutes.",
    featured: false,
    features: [
      "Everything in Lab, for every lab",
      "University single sign-on (SAML)",
      "Your institution's ethics and funding links built in",
      "Lab-level control over AI use",
      "Dedicated onboarding and support",
    ],
  },
];

export const INTEGRATIONS = [
  "Google Drive",
  "OneDrive",
  "Dropbox",
  "GitHub",
  "GitLab",
  "Overleaf",
  "Zotero",
  "REDCap",
  "Qualtrics",
  "OSF",
  "Zenodo",
  "Borealis",
];

export const AI_MODELS = [
  { name: "Claude", tag: "Supported" },
  { name: "ChatGPT", tag: "Supported" },
  { name: "Other MCP apps", tag: "Connector" },
  { name: "Your own API key", tag: "In-app" },
];

export const MODULES = [
  {
    title: "Projects",
    body: "Plan studies with goals, timelines, people and files connected from the start.",
    icon: "M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  },
  {
    title: "Tasks",
    body: "Boards and checklists that keep the whole team moving in the same direction.",
    icon: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9",
  },
  {
    title: "Notebook & protocols",
    body: "Versioned SOPs and lab notes, linked to the experiments that use them.",
    icon: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5",
  },
  {
    title: "Ethics tracking",
    body: "Applications, approvals, amendments and renewals in one organized place.",
    icon: "M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6zM9 12l2 2 4-4",
  },
  {
    title: "Funding & grants",
    body: "Deadlines, budgets and reports for every grant your lab holds.",
    icon: "M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  },
  {
    title: "Training records",
    body: "Required training per role, certificates on file, reminders before expiry.",
    icon: "M12 3l9 5-9 5-9-5zM6 10.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-5.5",
  },
  {
    title: "Inventory",
    body: "Equipment, reagents and licences with locations, orders and CSV export.",
    icon: "M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
  },
  {
    title: "Integrations",
    body: "Link files from Drive, OneDrive, GitHub, Zotero, REDCap and more.",
    icon: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  },
  {
    title: "Bring your own AI",
    body: "Use Claude, ChatGPT or your approved model across your lab work.",
    icon: "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  },
];
