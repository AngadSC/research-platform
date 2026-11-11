import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import { routes } from "@/routes";

export interface MockReq {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}
type Reply = { status?: number; body?: unknown };
type Handler = Reply | ((req: MockReq) => Reply);

/** Stubs global fetch. Keys look like "POST /api/labs/". Unknown requests fail the test loudly. */
export function mockFetch(handlers: Record<string, Handler>) {
  const calls: MockReq[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req: MockReq = {
      method: init?.method ?? "GET",
      path: String(input),
      body:
        init?.body instanceof FormData
          ? init.body
          : init?.body
            ? JSON.parse(String(init.body))
            : undefined,
      headers: (init?.headers ?? {}) as Record<string, string>,
    };
    calls.push(req);
    const h = handlers[`${req.method} ${req.path}`];
    if (!h) throw new Error(`Unmocked request: ${req.method} ${req.path}`);
    const { status = 200, body = null } = typeof h === "function" ? h(req) : h;
    return new Response(status === 204 ? null : body === null ? "" : JSON.stringify(body), {
      status,
    });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

export const SESSION_PATH = "/_allauth/browser/v1/auth/session";
export const SESSION = `GET ${SESSION_PATH}`;
export const signedOut = {
  status: 401,
  body: { status: 401, data: { flows: [{ id: "login" }] }, meta: { is_authenticated: false } },
};
export const signedIn = {
  status: 200,
  body: {
    status: 200,
    data: { user: { id: 1, email: "ada@uni.edu" } },
    meta: { is_authenticated: true },
  },
};

export function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

export const makeLab = (perms: string[], role = "pi") => ({
  id: "lab1",
  name: "Ada Lab",
  institution: { id: "i1", name: "Uni" },
  inventory_enabled: true,
  my_role: role,
  my_permissions: perms,
});
