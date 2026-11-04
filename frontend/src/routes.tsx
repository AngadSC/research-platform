import { Navigate, type RouteObject } from "react-router";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { CheckEmailPage, LoginPage, SignupPage, VerifyEmailPage } from "@/pages/AuthPages";
import { CreateLabPage } from "@/pages/CreateLabPage";
import { HomePage, NotBuiltPage } from "@/pages/HomePage";
import { LabHomePage } from "@/pages/LabHomePage";
import { MembersPage } from "@/pages/MembersPage";
import { SecurityPage } from "@/pages/SecurityPage";

export const routes: RouteObject[] = [
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
      { path: "/invite/:token", element: <AcceptInvitePage />, handle: { crumb: "Invitation" } },
    ],
  },
  {
    path: "/",
    element: <ProtectedLayout />,
    handle: { crumb: "Home" },
    children: [
      { index: true, element: <HomePage /> },
      { path: "account", element: <SecurityPage />, handle: { crumb: "Account" } },
      {
        path: "labs",
        handle: { crumb: "Labs" },
        children: [
          { index: true, element: <Navigate to="/" replace /> },
          { path: "new", element: <CreateLabPage />, handle: { crumb: "Create a lab" } },
          {
            path: ":labId",
            handle: { crumb: "@lab" },
            children: [
              { index: true, element: <LabHomePage /> },
              { path: "members", element: <MembersPage />, handle: { crumb: "Members" } },
              { path: "audit-log", element: <AuditLogPage />, handle: { crumb: "Audit log" } },
            ],
          },
        ],
      },
      { path: "*", element: <NotBuiltPage />, handle: { crumb: "Not available yet" } },
    ],
  },
];
