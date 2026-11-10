import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/lib/api";
import type {
  InstitutionResource,
  InstitutionResourceInput,
  InventoryImportResult,
  InventoryInput,
  InventoryItem,
  InventoryUsage,
  InventoryOrder,
  InventoryOrderInput,
  CalendarFeedCreated,
  CalendarFeedStatus,
  CalendarItem,
  Lab,
  LabEvent,
  LabEventInput,
  Meeting,
  MeetingInput,
  OnboardingItem,
  OnboardingItemInput,
  Protocol,
  ProtocolInput,
} from "@/lib/api-types";

const body = (v: unknown) => ({ body: v });
const base = (labId: string) => `/api/labs/${labId}`;

export interface LabDetailsInput {
  name?: string;
  institution_name?: string;
  department?: string;
  description?: string;
  address?: string;
  contact_email?: string;
  website?: string;
  inventory_enabled?: boolean;
}

export function useUpdateLabDetails(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: LabDetailsInput) =>
      api<Lab>(`${base(labId)}/`, { method: "PATCH", ...body(v) }),
    // starter links may have been added, so the resource lists are stale too
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs"] }),
  });
}

/** Generic list + create/update/delete for a lab collection under `path`. */
function useCollection<T, I>(labId: string, path: string, key: string, enabled = true, qs = "") {
  const qc = useQueryClient();
  const root = ["labs", labId, key];
  const done = () => qc.invalidateQueries({ queryKey: root });
  const url = `${base(labId)}/${path}/`;
  return {
    list: useQuery({
      queryKey: [...root, qs],
      queryFn: () => api<T[]>(`${url}${qs}`),
      enabled,
    }),
    create: useMutation({
      mutationFn: (v: I) => api<T>(url, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...v }: Partial<I> & { id: string }) =>
        api<T>(`${url}${id}/`, { method: "PATCH", ...body(v) }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`${url}${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}

export const useResources = (labId: string, category?: string, enabled = true) =>
  useCollection<InstitutionResource, InstitutionResourceInput>(
    labId,
    "institution-resources",
    "resources",
    enabled,
    category ? `?category=${encodeURIComponent(category)}` : "",
  );

export interface StartersLoaded {
  added: number;
  institution: string;
  curated_institution: string | null;
}

/** What loading the university's links did, in words. */
export function startersMessage(r: StartersLoaded) {
  const links = r.added === 1 ? "1 link" : `${r.added} links`;
  return r.curated_institution
    ? `Added ${links} for ${r.curated_institution}.`
    : `No curated forms for ${r.institution} yet. Added ${links} from the national funders.`;
}

/** "Get my university's forms" (D149): idempotent; needs manage_lab. */
export function useLoadStarters(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<StartersLoaded>(`${base(labId)}/institution-resources/load-starters/`, {
        method: "POST",
      }),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["labs", labId, "resources"] }),
        qc.invalidateQueries({ queryKey: ["labs", labId, "institution-resources"] }),
      ]),
  });
}

export function useOnboarding(labId: string, enabled = true) {
  const c = useCollection<OnboardingItem, OnboardingItemInput>(
    labId,
    "onboarding-items",
    "onboarding",
    enabled,
  );
  const qc = useQueryClient();
  const setDone = useMutation({
    mutationFn: (v: { itemId: string; user: string; done: boolean }) =>
      api<OnboardingItem>(`${base(labId)}/onboarding-items/${v.itemId}/completions/`, {
        method: "POST",
        ...body({ user: v.user, done: v.done }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "onboarding"] }),
  });
  return { ...c, setDone };
}

export interface InventoryQuery {
  q?: string;
  category?: string;
  ordering?: string;
}
export const inventoryQs = (p: InventoryQuery) => {
  const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]);
  return qs.size ? `?${qs}` : "";
};
export const inventoryExportUrl = (labId: string, p: InventoryQuery) =>
  `${base(labId)}/inventory/export/${inventoryQs(p)}`;

export const useInventory = (labId: string, p: InventoryQuery) =>
  useCollection<InventoryItem, InventoryInput>(
    labId,
    "inventory",
    "inventory",
    true,
    inventoryQs(p),
  );

/** Preview a CSV of inventory items, or (commit=true) add every row. */
export function importInventory(labId: string, file: File, commit: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("commit", String(commit));
  return upload<InventoryImportResult>(`${base(labId)}/inventory/import/`, form);
}

/** Protocols and records of use for a project (D228). */
export function useProtocols(labId: string, projectId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "protocols", projectId];
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<Protocol[]>(`${base(labId)}/projects/${projectId}/protocols/`),
  });
  const usage = useQuery({
    queryKey: [...key, "usage"],
    queryFn: () => api<InventoryUsage[]>(`${base(labId)}/projects/${projectId}/inventory-usage/`),
  });
  const done = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: key }),
      qc.invalidateQueries({ queryKey: ["labs", labId, "inventory"] }),
    ]);
  const save = useMutation({
    mutationFn: (v: { id?: string; body: ProtocolInput }) =>
      v.id
        ? api<Protocol>(`${base(labId)}/protocols/${v.id}/`, { method: "PATCH", ...body(v.body) })
        : api<Protocol>(`${base(labId)}/projects/${projectId}/protocols/`, {
            method: "POST",
            ...body(v.body),
          }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/protocols/${id}/`, { method: "DELETE" }),
    onSuccess: done,
  });
  const use = useMutation({
    mutationFn: (v: { protocol: string; reagent: string; amount: string; request_id: string }) =>
      api<InventoryUsage>(`${base(labId)}/protocols/${v.protocol}/use/`, {
        method: "POST",
        ...body({ reagent: v.reagent, amount: v.amount, request_id: v.request_id }),
      }),
    onSuccess: done,
  });
  const reverse = useMutation({
    mutationFn: (id: string) =>
      api<InventoryUsage>(`${base(labId)}/inventory-usage/${id}/reverse/`, { method: "POST" }),
    onSuccess: done,
  });
  return { list, usage, save, remove, use, reverse };
}

export const ordersExportUrl = (labId: string) => `${base(labId)}/inventory/orders/export/`;

export function useOrders(labId: string) {
  const qc = useQueryClient();
  const c = useCollection<InventoryOrder, InventoryOrderInput>(
    labId,
    "inventory/orders",
    "inventory-orders",
  );
  // Receiving an order changes an item's quantity.
  const refreshStock = () => qc.invalidateQueries({ queryKey: ["labs", labId, "inventory"] });
  return { ...c, refreshStock };
}

/** The month on screen: `list` is the merged calendar, the mutations are for lab events only. */
export function useCalendar(labId: string, from: string, to: string, mine = false) {
  const list = useQuery({
    queryKey: ["labs", labId, "calendar", from, to, mine],
    queryFn: () =>
      api<CalendarItem[]>(
        `${base(labId)}/calendar/?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}${mine ? "&mine=true" : ""}`,
      ),
  });
  // No GET on calendar/events/; a save refreshes the calendar queries above.
  const events = useCollection<LabEvent, LabEventInput>(
    labId,
    "calendar/events",
    "calendar",
    false,
  );
  const meetings = useCollection<Meeting, MeetingInput>(
    labId,
    "calendar/meetings",
    "calendar",
    false,
  );
  return { list, create: events.create, update: events.update, remove: events.remove, meetings };
}

/** Your secret calendar link for this lab: whether one exists, make or replace it, turn it off. */
export function useCalendarFeed(labId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "calendar-feed"];
  const url = `${base(labId)}/calendar/feed/`;
  const done = () => qc.invalidateQueries({ queryKey: key });
  return {
    status: useQuery({
      queryKey: key,
      queryFn: () => api<CalendarFeedStatus>(url),
    }),
    issue: useMutation({
      mutationFn: () => api<CalendarFeedCreated>(url, { method: "POST" }),
      onSuccess: done,
    }),
    revoke: useMutation({
      mutationFn: () => api(url, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}
