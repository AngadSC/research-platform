import { lazy, Suspense, type ComponentType } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Navigate, useParams, type RouteObject } from "react-router";
import { useLabs } from "@/hooks/workspace";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import {
  CheckEmailPage,
  LoginPage,
  ProviderCallbackPage,
  SignupPage,
  VerifyEmailPage,
} from "@/pages/AuthPages";
import { CreateLabPage } from "@/pages/CreateLabPage";
import { HomePage, LabListPage, NotFoundPage } from "@/pages/HomePage";
import { DocumentPage } from "@/pages/LazyDocumentPage";
import { LazyLineageTab } from "@/pages/project/LazyLineageTab";
import { LabHomePage } from "@/pages/LabHomePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LabChatPage } from "@/pages/LabChatPage";
import { LabDocumentsPage } from "@/pages/LabDocumentsPage";
import { MembersPage } from "@/pages/MembersPage";
import { MyWorkPage } from "@/pages/MyWorkPage";
import { FilesRedirect, ProjectPage, ProjectTab } from "@/pages/ProjectPage";
import DocumentsTab from "@/pages/project/DocumentsTab";
import ExternalTab from "@/pages/project/ExternalTab";
import LazyAnalyse from "@/pages/project/analyse/LazyAnalyse";
import PdfViewerRoute from "@/pages/project/PdfViewerRoute";
import OverviewTab from "@/pages/project/OverviewTab";
import { ResearchDetail, ResearchNew } from "@/pages/project/ResearchTab";
import TasksTab from "@/pages/project/TasksTab";
import EthicsTab from "@/pages/project/workflow/EthicsTab";
import FundingTab from "@/pages/project/workflow/FundingTab";
import ProtocolsTab from "@/pages/project/workflow/ProtocolsTab";
import ParticipantsTab from "@/pages/project/workflow/ParticipantsTab";
import { ParticipantsOverviewPage } from "@/pages/ParticipantsOverviewPage";
import ParticipantPage from "@/pages/project/participants/ParticipantPage";
import NotebookTab from "@/pages/project/NotebookTab";
import { NotebookPage } from "@/pages/NotebookPage";
import SubjectsTab from "@/pages/project/SubjectsTab";
import ParticipantRegistry from "@/pages/project/participants/ParticipantRegistry";
import ReviewTab from "@/pages/project/workflow/ReviewTab";
import {
  AnalysisTab,
  DataTab,
  LineageRedirect,
  ManuscriptTab,
  ResearchRedirect,
  WorkflowIndex,
  WorkflowLayout,
} from "@/pages/project/workflow/WorkflowLayout";
import { IntegrationsErrorPage, IntegrationsPage } from "@/pages/IntegrationsPage";
import { MarketingLayout } from "@/pages/landing/MarketingLayout";
import { FeaturesPage } from "@/pages/landing/pages/FeaturesPage";
import { InstitutionsPage } from "@/pages/landing/pages/InstitutionsPage";
import { LabsPage } from "@/pages/landing/pages/LabsPage";
import { PrivacyPage, TermsPage, ZoomHelpPage } from "@/pages/landing/pages/LegalPages";
import { PricingPage } from "@/pages/landing/pages/PricingPage";
import { StudentsPage } from "@/pages/landing/pages/StudentsPage";
import { WorkflowPage } from "@/pages/landing/pages/WorkflowPage";

/** Less-visited pages load when first opened, so Home ships without them. */
function later<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  const Page = lazy(async () => ({ default: (await load())[name] as ComponentType }));
  return function LazyPage() {
    return (
      <Suspense
        fallback={
          <div className="grid gap-3 p-8" aria-busy="true" aria-label="Loading">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-80" />
          </div>
        }
      >
        <Page />
      </Suspense>
    );
  };
}
const AuditLogPage = later(() => import("@/pages/AuditLogPage"), "AuditLogPage");
const FundingPage = later(() => import("@/pages/FundingPage"), "FundingPage");
const TeamTasksPage = later(() => import("@/pages/TeamTasksPage"), "TeamTasksPage");
const CalendarPage = later(() => import("@/pages/CalendarPage"), "CalendarPage");
const HandoverPage = later(() => import("@/pages/HandoverPage"), "HandoverPage");
const HelpPage = later(() => import("@/pages/HelpPage"), "HelpPage");
const SettingsPage = later(() => import("@/pages/SettingsPage"), "SettingsPage");
const OAuthConsentPage = later(() => import("@/pages/OAuthConsentPage"), "OAuthConsentPage");
const AdminPage = later(() => import("@/pages/admin/AdminPage"), "AdminPage");
const InventoryPage = later(() => import("@/pages/admin/InventoryPage"), "InventoryPage");
const PaperDetailPage = later(() => import("@/pages/papers/PaperDetailPage"), "PaperDetailPage");
const PapersPage = later(() => import("@/pages/papers/PapersPage"), "PapersPage");
const MyTrainingPage = later(() => import("@/pages/training/MyTrainingPage"), "MyTrainingPage");
const EthicsDetailPage = later(() => import("@/pages/ethics/EthicsPages"), "EthicsDetailPage");
const EthicsFormPage = later(() => import("@/pages/ethics/EthicsPages"), "EthicsFormPage");
const EthicsListPage = later(() => import("@/pages/ethics/EthicsPages"), "EthicsListPage");
const NotificationsPage = later(() => import("@/pages/ethics/LabPages"), "NotificationsPage");
const RetentionPage = later(() => import("@/pages/ethics/LabPages"), "RetentionPage");
const UsagePage = later(() => import("@/pages/UsagePage"), "UsagePage");

/** /labs/<lab>/settings: lab admins get Lab details; everyone else gets their own Settings. */
function LabSettingsRedirect() {
  const { labId } = useParams();
  const { data: labs } = useLabs();
  if (!labs) return null;
  const canManage = labs.find((l) => l.id === labId)?.my_permissions.includes("manage_lab");
  return <Navigate to={canManage ? "../admin" : "/settings"} relative="path" replace />;
}

export const routes: RouteObject[] = [
  {
    // Public marketing pages. Open to everyone, signed in or not; the home page is "/" below.
    element: <MarketingLayout />,
    children: [
      { path: "/features", element: <FeaturesPage /> },
      { path: "/workflow", element: <WorkflowPage /> },
      { path: "/for-labs", element: <LabsPage /> },
      { path: "/for-students", element: <StudentsPage /> },
      { path: "/for-institutions", element: <InstitutionsPage /> },
      { path: "/pricing", element: <PricingPage /> },
      { path: "/privacy", element: <PrivacyPage /> },
      { path: "/terms", element: <TermsPage /> },
      { path: "/zoom", element: <ZoomHelpPage /> },
    ],
  },
  {
    element: <AuthLayout />,
    children: [
      { path: "/login", element: <LoginPage />, handle: { crumb: "Sign in" } },
      { path: "/signup", element: <SignupPage />, handle: { crumb: "Create account" } },
      { path: "/check-email", element: <CheckEmailPage />, handle: { crumb: "Check your email" } },
      {
        path: "/account/verify-email/:key",
        element: <VerifyEmailPage />,
        handle: { crumb: "Confirm email" },
      },
      {
        path: "/account/provider/callback",
        element: <ProviderCallbackPage />,
        handle: { crumb: "Sign in" },
      },
      { path: "/invite/:token", element: <AcceptInvitePage />, handle: { crumb: "Invitation" } },
    ],
  },
  {
    path: "/",
    element: <ProtectedLayout />,
    handle: { crumb: "Home" },
    children: [
      { index: true, element: <HomePage /> },
      { path: "settings", element: <SettingsPage />, handle: { crumb: "Settings" } },
      { path: "help", element: <HelpPage />, handle: { crumb: "Help" } },
      { path: "usage", element: <UsagePage />, handle: { crumb: "Usage" } },
      // The account menu's Profile: the Profile tab of Settings.
      { path: "profile", element: <Navigate to="/settings#profile" replace /> },
      // D161: OAuth authorization endpoint for MCP clients (sign-in and MFA happen first)
      {
        path: "oauth/authorize",
        element: <OAuthConsentPage />,
        handle: { crumb: "Connect an AI app" },
      },
      // Run 4: Account and Security moved into Settings; the old address still works.
      { path: "account", element: <Navigate to="/settings#security" replace /> },
      {
        path: "integrations/error",
        element: <IntegrationsErrorPage />,
        handle: { crumb: "Integrations" },
      },
      {
        path: "labs",
        handle: { crumb: "Labs" },
        children: [
          { index: true, element: <LabListPage /> },
          { path: "new", element: <CreateLabPage />, handle: { crumb: "Create a lab" } },
          {
            path: ":labId",
            handle: { crumb: "@lab" },
            children: [
              { index: true, element: <Navigate to="dashboard" replace /> },
              { path: "dashboard", element: <DashboardPage />, handle: { crumb: "Home" } },
              { path: "my-work", element: <MyWorkPage />, handle: { crumb: "My work" } },
              { path: "notebook", element: <NotebookPage />, handle: { crumb: "My notebook" } },
              {
                path: "participants",
                element: <ParticipantsOverviewPage />,
                handle: { crumb: "Participants" },
              },
              {
                path: "documents",
                handle: { crumb: "Lab documents" },
                children: [
                  { index: true, element: <LabDocumentsPage /> },
                  {
                    path: ":documentId",
                    element: <DocumentPage />,
                    handle: { crumb: "@document" },
                  },
                ],
              },
              { path: "my-tasks", element: <Navigate to="../my-work" relative="path" replace /> },
              {
                path: "members",
                handle: { crumb: "Members" },
                children: [
                  { index: true, element: <MembersPage /> },
                  {
                    path: ":membershipId/handover",
                    element: <HandoverPage />,
                    handle: { crumb: "Handover" },
                  },
                ],
              },
              {
                path: "projects",
                handle: { crumb: "Projects" },
                children: [
                  { index: true, element: <LabHomePage /> },
                  {
                    path: ":projectId",
                    element: <ProjectPage />,
                    handle: { crumb: "@project" },
                    children: [
                      { index: true, element: <Navigate to="overview" replace /> },
                      {
                        path: "overview",
                        element: <ProjectTab as={OverviewTab} />,
                        handle: { crumb: "Overview" },
                      },
                      {
                        path: "handover",
                        element: <HandoverPage />,
                        handle: { crumb: "Handover" },
                      },
                      {
                        path: "tasks",
                        element: <ProjectTab as={TasksTab} />,
                        handle: { crumb: "Tasks" },
                      },
                      {
                        path: "participants",
                        handle: { crumb: "Participants" },
                        children: [
                          { index: true, element: <ProjectTab as={ParticipantRegistry} /> },
                          {
                            path: ":participantId",
                            element: <ProjectTab as={ParticipantPage} />,
                            handle: { crumb: "Participant" },
                          },
                        ],
                      },
                      {
                        path: "notebook",
                        element: <ProjectTab as={NotebookTab} />,
                        handle: { crumb: "Notebook" },
                      },
                      {
                        path: "subjects",
                        element: <ProjectTab as={SubjectsTab} />,
                        handle: { crumb: "Subjects" },
                      },
                      // Chat is a side panel over any section; old links open it.
                      {
                        path: "chat",
                        element: <Navigate to="../overview?chat=1" relative="path" replace />,
                      },
                      {
                        path: "external",
                        element: <ProjectTab as={ExternalTab} />,
                        handle: { crumb: "Presentations" },
                      },
                      {
                        path: "documents",
                        handle: { crumb: "Documents and files" },
                        children: [
                          { index: true, element: <ProjectTab as={DocumentsTab} /> },
                          {
                            path: ":documentId",
                            element: <DocumentPage />,
                            handle: { crumb: "@document" },
                          },
                        ],
                      },
                      {
                        path: "files",
                        handle: { crumb: "Documents and files" },
                        children: [
                          // Files share the Documents tab; a PDF still opens at files/<id>.
                          { index: true, element: <FilesRedirect /> },
                          {
                            path: ":attachmentId",
                            element: <PdfViewerRoute />,
                            handle: { crumb: "View file" },
                          },
                        ],
                      },
                      {
                        path: "analyse",
                        element: <ProjectTab as={LazyAnalyse} />,
                        handle: { crumb: "Statistics" },
                      },
                      { path: "lineage", element: <LineageRedirect /> },
                      // D132: the old Research tab is the Workflow tab; its addresses redirect.
                      { path: "research/*", element: <ResearchRedirect /> },
                      {
                        path: "workflow",
                        handle: { crumb: "Workflow" },
                        element: <ProjectTab as={WorkflowLayout} />,
                        children: [
                          { index: true, element: <ProjectTab as={WorkflowIndex} /> },
                          {
                            path: "lineage",
                            element: <ProjectTab as={LazyLineageTab} />,
                            handle: { crumb: "Lineage" },
                          },
                          {
                            path: "protocols",
                            element: <ProjectTab as={ProtocolsTab} />,
                            handle: { crumb: "Protocols" },
                          },
                          {
                            path: "funding",
                            element: <ProjectTab as={FundingTab} />,
                            handle: { crumb: "Funding" },
                          },
                          {
                            path: "ethics",
                            element: <ProjectTab as={EthicsTab} />,
                            handle: { crumb: "Ethics" },
                          },
                          {
                            path: "participants",
                            element: <ProjectTab as={ParticipantsTab} />,
                            handle: { crumb: "Participants" },
                          },
                          ...(
                            [
                              ["data", "Data", DataTab],
                              ["analysis", "Analysis", AnalysisTab],
                              ["manuscript", "Manuscript", ManuscriptTab],
                              ["review", "Review", ReviewTab],
                            ] as const
                          ).map(([path, crumb, Tab]) => ({
                            path,
                            handle: { crumb },
                            children: [
                              { index: true, element: <ProjectTab as={Tab} /> },
                              {
                                path: ":kind",
                                handle: { crumb: "@kind" },
                                children: [
                                  {
                                    index: true,
                                    element: <Navigate to=".." relative="path" replace />,
                                  },
                                  {
                                    path: "new",
                                    element: <ProjectTab as={ResearchNew} />,
                                    handle: { crumb: "New" },
                                  },
                                  {
                                    path: ":id",
                                    element: <ProjectTab as={ResearchDetail} />,
                                    handle: { crumb: "@record" },
                                  },
                                ],
                              },
                            ],
                          })),
                        ],
                      },
                    ],
                  },
                ],
              },
              {
                path: "ethics",
                handle: { crumb: "Ethics approvals" },
                children: [
                  { index: true, element: <EthicsListPage /> },
                  { path: "new", element: <EthicsFormPage />, handle: { crumb: "New" } },
                  {
                    path: ":approvalId",
                    handle: { crumb: "@approval" },
                    children: [
                      { index: true, element: <EthicsDetailPage /> },
                      { path: "edit", element: <EthicsFormPage />, handle: { crumb: "Edit" } },
                      {
                        path: "files/:attachmentId",
                        element: <PdfViewerRoute />,
                        handle: { crumb: "View file" },
                      },
                    ],
                  },
                ],
              },
              {
                path: "notifications",
                element: <NotificationsPage />,
                handle: { crumb: "Notifications" },
              },
              {
                path: "retention",
                element: <RetentionPage />,
                handle: { crumb: "Retention review" },
              },
              { path: "audit-log", element: <AuditLogPage />, handle: { crumb: "Audit log" } },
              { path: "funding", element: <FundingPage />, handle: { crumb: "Funding" } },
              {
                path: "team-tasks",
                element: <TeamTasksPage />,
                handle: { crumb: "Team tasks" },
              },
              { path: "admin", element: <AdminPage />, handle: { crumb: "Lab details" } },
              // Guessable addresses for pages that live elsewhere.
              { path: "settings", element: <LabSettingsRedirect /> },
              { path: "integrations", element: <Navigate to="../settings/integrations" replace /> },
              { path: "inventory", element: <InventoryPage />, handle: { crumb: "Inventory" } },
              { path: "chat", element: <LabChatPage />, handle: { crumb: "Lab chat" } },
              { path: "calendar", element: <CalendarPage />, handle: { crumb: "Calendar" } },
              {
                path: "papers",
                handle: { crumb: "Papers" },
                children: [
                  { index: true, element: <PapersPage /> },
                  {
                    path: ":paperId",
                    handle: { crumb: "@paper" },
                    children: [
                      { index: true, element: <PaperDetailPage /> },
                      { path: "pdf", element: <PdfViewerRoute />, handle: { crumb: "View PDF" } },
                    ],
                  },
                ],
              },
              { path: "training", element: <MyTrainingPage />, handle: { crumb: "Training" } },
              {
                path: "settings/integrations",
                element: <IntegrationsPage />,
                handle: { crumb: "Integrations" },
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage />, handle: { crumb: "Not found" } },
    ],
  },
];
