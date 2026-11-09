# ruff: noqa: E501
"""Starter links per institution (D126, D149). Only URLs that were fetched and confirmed to be
the official page are listed; nothing is guessed. Checked 2026-11-08 (HTTP request and page read,
final URL after redirects). `ualberta.ca` and McGill's eRAP page answer 403 to scripted requests,
so those were confirmed by reading the page through a web-fetch service instead."""

import re
import unicodedata

UALBERTA = "University of Alberta"
UBC = "University of British Columbia"
UCALGARY = "University of Calgary"
DALHOUSIE = "Dalhousie University"
LAVAL = "Université Laval"
UMANITOBA = "University of Manitoba"
MCGILL = "McGill University"
MCMASTER = "McMaster University"
UMONTREAL = "Université de Montréal"
UOTTAWA = "University of Ottawa"
QUEENS = "Queen's University"
USASK = "University of Saskatchewan"
UTORONTO = "University of Toronto"
UWATERLOO = "University of Waterloo"
WESTERN = "Western University"

# Every lab gets these, whatever its institution.
NATIONAL_RESOURCES = [
    {
        "category": "ethics",
        "title": "TCPS 2 (2022): Ethical Conduct for Research Involving Humans",
        "url": "https://ethics.gc.ca/eng/policy-politique_tcps2-eptc2_2022.html",
        "description": "The Tri-Council Policy Statement on research involving humans.",
    },
    {
        "category": "ethics",
        "title": "TCPS 2: CORE-2022 tutorial",
        "url": "https://www.tcps2core.ca/welcome",
        "description": "The online Course on Research Ethics and its certificate of completion.",
    },
    {
        "category": "funding",
        "title": "CIHR: index of funding related forms",
        "url": "https://cihr-irsc.gc.ca/e/797.html",
        "description": "Forms and completion instructions used in CIHR applications.",
    },
    {
        "category": "funding",
        "title": "CIHR: grants application guidelines",
        "url": "https://cihr-irsc.gc.ca/e/50454.html",
        "description": "How to complete and submit a grant application in ResearchNet.",
    },
    {
        "category": "funding",
        "title": "NSERC: On-line System PDF forms and instructions",
        "url": "https://nserc-crsng.canada.ca/en/funding/online-application-systems-and-tools/online-services/on-line-system-pdf-forms-and",
        "description": "Instructions for NSERC application forms, by form number.",
    },
    {
        "category": "funding",
        "title": "SSHRC: forms and online application tools",
        "url": "https://sshrc-crsh.canada.ca/en/funding/forms-and-online-application-tools.aspx",
        "description": "Forms and online tools to apply for, receive and report on SSHRC funding.",
    },
    {
        "category": "funding",
        "title": "Tri-agency Guide on Financial Administration",
        "url": "https://nserc-crsng.canada.ca/en/funding/research-partnerships-and-collaborations/inter-agency/tri-agency-financial-administration-1",
        "description": "Rules for administering CIHR, NSERC and SSHRC grants.",
    },
    {
        "category": "data_management",
        "title": "Tri-Agency Research Data Management Policy",
        "url": "https://science.gc.ca/site/science/en/interagency-research-funding/policies-and-guidelines/research-data-management/tri-agency-research-data-management-policy",
        "description": "Requirements for institutional strategies, data management plans and data deposit.",
    },
]

STARTER_RESOURCES = {
    UALBERTA: [
        {
            "category": "ethics",
            "title": "Research Ethics Office",
            "url": "https://www.ualberta.ca/en/research/services/research-ethics/index.html",
            "description": "Reviews human participant research, animal research and financial conflicts of interest.",
        },
        {
            "category": "ethics",
            "title": "ARISE ethics application system",
            "url": "https://www.ualberta.ca/en/research/services/research-ethics/arise-support.html",
            "description": "How to get access to ARISE, with training, tutorials and FAQs.",
        },
        {
            "category": "ethics",
            "title": "Forms Cabinet",
            "url": "https://www.ualberta.ca/en/research/services/research-ethics/forms-cabinet.html",
            "description": "Guidance documents and consent templates for ethics applications.",
        },
        {
            "category": "funding",
            "title": "Internal research funding",
            "url": "https://www.ualberta.ca/en/research/services/funding-awards/funding-opportunities/internal-research-funding.html",
            "description": "Internal grant programs with eligibility, deadlines and terms of reference.",
        },
        {
            "category": "funding",
            "title": "Institutional approval for grant applications",
            "url": "https://www.ualberta.ca/en/research/services/develop-and-submit-proposal/institutional-approval-for-grant-applications.html",
            "description": "How Research Administrative Services reviews and signs external grant applications.",
        },
        {
            "category": "data_management",
            "title": "Institutional Research Data Management Strategy",
            "url": "https://www.ualberta.ca/en/research-innovation/plans-reports-policies/institutional-research-data-management-strategy.html",
            "description": "The university's roadmap for research data management.",
        },
    ],
    UBC: [
        {
            "category": "ethics",
            "title": "How to obtain ethics approval",
            "url": "https://researchethics.ubc.ca/about-human-research-ethics/how-obtain-ethics-approval",
            "description": "Which UBC research ethics board to apply to; applications are submitted through RISe.",
        },
        {
            "category": "ethics",
            "title": "RISe sample ethics forms",
            "url": "https://www.rise.ubc.ca/sample-forms-and-rise-sandbox",
            "description": "PDF samples of ethics application forms, for reference; applications are made in RISe.",
        },
        {
            "category": "funding",
            "title": "Submitting a grant application (Office of Research Services)",
            "url": "https://ors.ubc.ca/submitting-grant-application",
            "description": "The signed Research Project Information Form, internal deadlines and required signatures.",
        },
        {
            "category": "funding",
            "title": "Submitting your proposal",
            "url": "https://research.ubc.ca/support-researchers/attracting-funding/submitting-your-proposal",
            "description": "RISe, the Research Project Information Form and institutional signatures.",
        },
        {
            "category": "data_management",
            "title": "UBC's RDM Strategy",
            "url": "https://rdm.ubc.ca/about/ubcs-rdm-strategy",
            "description": "UBC's institutional research data management strategy.",
        },
    ],
    UCALGARY: [
        {
            "category": "ethics",
            "title": "IRISS",
            "url": "https://research.ucalgary.ca/iriss",
            "description": "The online system for ethics applications, approvals and certificates.",
        },
        {
            "category": "ethics",
            "title": "Ethics resources",
            "url": "https://research.ucalgary.ca/research-services/design-and-implement/ethics-compliance/ethics-resources",
            "description": "CFREB and CHREB forms, templates and guidance.",
        },
        {
            "category": "funding",
            "title": "Internal grants",
            "url": "https://research.ucalgary.ca/research-services/find-and-manage-funding/internal-grants",
            "description": "Vice-President (Research) grant programs.",
        },
        {
            "category": "funding",
            "title": "Guidelines for obtaining institutional signatures",
            "url": "https://research.ucalgary.ca/research-services/find-and-manage-funding/signatures",
            "description": "What each signature on a grant application means.",
        },
        {
            "category": "data_management",
            "title": "UCalgary RDM Strategy",
            "url": "https://research.ucalgary.ca/research-services/additional-resources/research-data-management/rdm-strategy",
            "description": "The university's research data management strategy.",
        },
    ],
    DALHOUSIE: [
        {
            "category": "ethics",
            "title": "Apply for research ethics board approval",
            "url": "https://www.dal.ca/research-and-innovation/support-for-researchers/responsible-conduct-research/human-ethics/ethics-board-approval.html",
            "description": "Application forms, instructions, consent templates and deadlines.",
        },
        {
            "category": "funding",
            "title": "Internal funding",
            "url": "https://www.dal.ca/research-and-innovation/support-for-researchers/internal-funding.html",
            "description": "Internal funding opportunities from the Vice-President Research and Innovation.",
        },
    ],
    LAVAL: [
        {
            "category": "ethics",
            "title": "Formulaire et documents à fournir (CÉRUL)",
            "url": "https://www.cerul.ulaval.ca/depot-dune-demande-et-suivi-dun-projet/formulaire-et-documents-a-fournir/",
            "description": "Formulaires de demande d'approbation éthique et documents à joindre.",
        },
        {
            "category": "funding",
            "title": "Préparer une demande de financement",
            "url": "https://www.services-recherche.ulaval.ca/financement/preparer-une-demande-de-financement",
            "description": "Vérifications internes, signatures requises et dépôt d'une demande.",
        },
    ],
    UMANITOBA: [
        {
            "category": "ethics",
            "title": "Human research ethics",
            "url": "https://umanitoba.ca/research/opportunities-support/ethics-compliance/ethics/fort-garry",
            "description": "Required documents, consent templates and how to apply.",
        },
        {
            "category": "ethics",
            "title": "Research Administration System (RAS)",
            "url": "https://www.umanitoba.ca/research/opportunities-support/research-administration-system-ras",
            "description": "The system for human research ethics submissions, with user guides.",
        },
        {
            "category": "funding",
            "title": "Funding Application Approval Form (FAAF)",
            "url": "https://umanitoba.ca/research/office-research-services/funding-application-approval-form-faaf",
            "description": "The approval form and submission process for grant applications.",
        },
    ],
    MCGILL: [
        {
            "category": "ethics",
            "title": "eRAP: Electronic Research Administration Portal",
            "url": "https://www.mcgill.ca/research/research/human/erap",
            "description": "The system for submitting human research ethics applications.",
        },
        {
            "category": "ethics",
            "title": "Forms and guidelines (Social Science Behavioural REBs)",
            "url": "https://www.mcgill.ca/research/research/human/ssbreb/forms-and-guidelines",
            "description": "Mandatory training, consent template and guidelines.",
        },
        {
            "category": "ethics",
            "title": "Forms, guidelines and training (Faculty of Medicine and Health Sciences REB)",
            "url": "https://www.mcgill.ca/research/research/human/fmhsreb/forms-guidelines-and-training",
            "description": "Assurance forms, scientific review form and consent guidelines.",
        },
        {
            "category": "funding",
            "title": "Internal funding",
            "url": "https://www.mcgill.ca/research/research/funding/internal",
            "description": "Internal research funds, with guidelines and application forms.",
        },
        {
            "category": "funding",
            "title": "Getting signatures",
            "url": "https://www.mcgill.ca/research/research/proposal/signatures",
            "description": "Institutional review and signatures, including the Research Funding Checklist.",
        },
        {
            "category": "data_management",
            "title": "McGill Institutional RDM Strategy",
            "url": "https://www.mcgill.ca/drs/rdm/about-rdm-strategy",
            "description": "McGill's institutional research data management strategy.",
        },
    ],
    MCMASTER: [
        {
            "category": "ethics",
            "title": "MacREM",
            "url": "https://research.mcmaster.ca/home/support-for-researchers/ethics/macrem/",
            "description": "The online system for McMaster Research Ethics Board applications.",
        },
        {
            "category": "ethics",
            "title": "MREB templates and guides",
            "url": "https://research.mcmaster.ca/home/support-for-researchers/ethics/macrem/macrem-templates/",
            "description": "Consent, recruitment and application templates.",
        },
        {
            "category": "funding",
            "title": "Research Office for Administration, Development and Support (ROADS)",
            "url": "https://research.mcmaster.ca/research-office-for-administration-development-and-support-roads/",
            "description": "Grant application approval forms, by faculty.",
        },
    ],
    UMONTREAL: [
        {
            "category": "ethics",
            "title": "Démarches auprès de votre comité d'éthique",
            "url": "https://crr.umontreal.ca/fr/ethique-humaine/demarches-aupres-de-votre-comite/",
            "description": "Comités d'éthique de la recherche, formulaires, dates de dépôt et accès à Nagano.",
        },
        {
            "category": "funding",
            "title": "Préparer votre demande",
            "url": "https://recherche.umontreal.ca/ressources/subventions-de-recherche/preparer-votre-demande/",
            "description": "Préparation d'une demande de subvention et signature institutionnelle.",
        },
        {
            "category": "funding",
            "title": "Formulaires, procédures, rapports et accès aux systèmes",
            "url": "https://recherche.umontreal.ca/ressources/subventions-de-recherche/gerer-vos-fonds-de-recherche/formulaires-procedures-rapports-et-acces-aux-systemes/",
            "description": "Formulaires et procédures pour la gestion des fonds de recherche.",
        },
    ],
    UOTTAWA: [
        {
            "category": "ethics",
            "title": "Forms and templates (Research Ethics)",
            "url": "https://www.uottawa.ca/research-innovation/ethics/forms-templates",
            "description": "eReviews, consent templates and course-based research forms.",
        },
        {
            "category": "funding",
            "title": "Internal funding opportunities",
            "url": "https://www.uottawa.ca/research-innovation/research-management-services/internal-funding-opportunities",
            "description": "Competitive internal research funding programs.",
        },
    ],
    QUEENS: [
        {
            "category": "ethics",
            "title": "Ethics application and event forms",
            "url": "https://www.queensu.ca/research/ethics/forms",
            "description": "Fillable GREB and HSREB application and event forms.",
        },
        {
            "category": "funding",
            "title": "Internal funding",
            "url": "https://www.queensu.ca/research/funding/internal",
            "description": "Internal programs from the Vice-Principal Research.",
        },
        {
            "category": "funding",
            "title": "TRAQ DSS form requirement",
            "url": "https://www.queensu.ca/secretariat/policies/research-policies/research-administration-policy/traq-dss-form-requirement",
            "description": "The form and internal deadlines for research funding proposals.",
        },
        {
            "category": "data_management",
            "title": "Research Data Management Institutional Strategy",
            "url": "https://www.queensu.ca/research/data-management/strategy",
            "description": "Queen's institutional research data management strategy.",
        },
    ],
    USASK: [
        {
            "category": "ethics",
            "title": "Human Research Ethics Office",
            "url": "https://vpresearch.usask.ca/ethics/human-ethics.php",
            "description": "Behavioural and biomedical application forms and consent templates.",
        },
        {
            "category": "funding",
            "title": "Apply for funding",
            "url": "https://vpresearch.usask.ca/rasi/grant-support/apply-for-funding.php",
            "description": "Institutional approval through UnivRS and internal deadlines.",
        },
        {
            "category": "funding",
            "title": "USask internal grants programs",
            "url": "https://vpresearch.usask.ca/rasi/find-funding/usask-internal-grants-programs.php",
            "description": "Internal funding programs for faculty research.",
        },
        {
            "category": "data_management",
            "title": "Research Data Management",
            "url": "https://vpresearch.usask.ca/research-support/research-data-management.php",
            "description": "USask's research data management strategy and roadmap.",
        },
    ],
    UTORONTO: [
        {
            "category": "ethics",
            "title": "Submit a human ethics protocol",
            "url": "https://research.utoronto.ca/ethics-human-research/submit-human-ethics-protocol",
            "description": "Submission route, deadlines and guidelines; submissions are made in My Research Human Protocols.",
        },
        {
            "category": "ethics",
            "title": "My Research Human Protocols (MRHP)",
            "url": "https://research.utoronto.ca/my-research-system-help-support/my-research-human-protocols-mrhp",
            "description": "Access, user guides and the protocol worksheet for the ethics system.",
        },
        {
            "category": "funding",
            "title": "Apply for funding",
            "url": "https://research.utoronto.ca/applying-research-funding/overview",
            "description": "The process for applying for research funding and institutional endorsement.",
        },
        {
            "category": "funding",
            "title": "My Research Applications and Agreements (MRA)",
            "url": "https://research.utoronto.ca/my-research-system-help-support/my-research-applications-agreements-mra",
            "description": "The system for internal review and endorsement of funding applications.",
        },
        {
            "category": "data_management",
            "title": "Institutional Research Data Management Strategy",
            "url": "https://research.utoronto.ca/engaging-research/university-toronto-institutional-research-data-management-strategy",
            "description": "U of T's institutional research data management strategy.",
        },
    ],
    UWATERLOO: [
        {
            "category": "ethics",
            "title": "Application process for research with human participants",
            "url": "https://uwaterloo.ca/research-ethics/research-human-participants/application-process-research-human-participants",
            "description": "The five steps for submitting an ethics application.",
        },
        {
            "category": "ethics",
            "title": "Research ethics system login and updates",
            "url": "https://uwaterloo.ca/research-ethics/research-ethics-system-login",
            "description": "The online Research Ethics System and recent guideline changes.",
        },
        {
            "category": "funding",
            "title": "Apply for funding",
            "url": "https://uwaterloo.ca/research/find-and-apply-funding/apply-funding",
            "description": "Office of Research review before an application goes to the sponsor.",
        },
        {
            "category": "funding",
            "title": "Forms (Office of Research)",
            "url": "https://uwaterloo.ca/research/resources/forms",
            "description": "Cover sheet, internal nomination forms and other research forms.",
        },
        {
            "category": "data_management",
            "title": "Research Data Management Institutional Strategy",
            "url": "https://uwaterloo.ca/research/resources/research-data-management-institutional-strategy",
            "description": "Waterloo's institutional research data management strategy.",
        },
    ],
    WESTERN: [
        {
            "category": "ethics",
            "title": "Western Research Ethics Manager (WREM)",
            "url": "https://www.uwo.ca/research/compliance/human-research-ethics/wrem.html",
            "description": "The protocol submission platform for Western's research ethics boards.",
        },
        {
            "category": "ethics",
            "title": "Submitting to research ethics boards",
            "url": "https://www.uwo.ca/research/compliance/human-research-ethics/submissions.html",
            "description": "Which board to apply to and how to submit.",
        },
        {
            "category": "funding",
            "title": "Internal funding",
            "url": "https://www.uwo.ca/research/funding/internal/index.html",
            "description": "Internal funding opportunities sponsored by Western Research.",
        },
        {
            "category": "funding",
            "title": "ROLA process",
            "url": "https://www.uwo.ca/research/support/resources/rola/rola-process.html",
            "description": "Internal electronic approvals for funding applications.",
        },
        {
            "category": "data_management",
            "title": "Research Data Management at Western",
            "url": "https://rdm.uwo.ca/",
            "description": "Western's research data management site.",
        },
    ],
}

# Exact matches only, after _key(). "U of C" and "U of M" are left out on purpose: they also mean
# Chicago, Michigan, Manitoba or Montréal, and a wrong match renames the lab's institution.
ALIASES = {
    UALBERTA: ["U of A", "UofA", "UAlberta", "Alberta"],  # D126: the founder's "UofA"
    UBC: ["UBC", "British Columbia"],
    UCALGARY: ["UCalgary", "Calgary"],
    DALHOUSIE: ["Dalhousie", "Dal"],
    LAVAL: ["Laval", "ULaval", "University Laval", "Laval University"],
    UMANITOBA: ["UManitoba", "Manitoba"],
    MCGILL: ["McGill"],
    MCMASTER: ["McMaster"],
    UMONTREAL: ["UdeM", "U de M", "University of Montreal", "Montreal"],
    UOTTAWA: ["uOttawa", "U Ottawa", "Ottawa", "Université d'Ottawa"],
    QUEENS: ["Queen's", "Queen's University at Kingston"],
    USASK: ["USask", "U of S", "Saskatchewan"],
    UTORONTO: ["U of T", "UofT", "UToronto", "Toronto"],
    UWATERLOO: ["UWaterloo", "Waterloo"],
    WESTERN: ["Western", "UWO", "University of Western Ontario", "Western Ontario"],
}


def _key(name: str) -> str:
    """Lower case without accents, apostrophes or dots, so "Queen’s" and "QUEENS" compare equal."""
    text = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    ).casefold()
    text = re.sub(r"['’.]", "", text)
    return re.sub(r"^the\s+", "", re.sub(r"[^a-z0-9]+", " ", text).strip())


_NAMES = {_key(n): n for n in STARTER_RESOURCES} | {
    _key(alias): name for name, aliases in ALIASES.items() for alias in aliases
}


def match_institution(name: str) -> str | None:
    """The curated institution this typed name means, or None when there is no curated set."""
    return _NAMES.get(_key(name))
