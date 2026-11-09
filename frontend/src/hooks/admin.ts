import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  InstitutionResource,
  InstitutionResourceInput,
  InventoryInput,
  InventoryItem,
  Lab,
  OnboardingItem,
  OnboardingItemInput,
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
