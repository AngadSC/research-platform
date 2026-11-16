import { ArrowDown, ArrowUp, Eye, EyeOff, Plus, RotateCcw, X, type LucideIcon } from "lucide-react";
import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { applyOrder } from "@/components/layout/holdToReorder";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useLayout, useSidebarOrder } from "@/hooks/preferences";
import { useLabs } from "@/hooks/workspace";
import { navKey, shortcutId, TOPBAR_BUILTIN } from "@/lib/layout";
import { navItems } from "@/lib/nav";
import { Section } from "@/pages/admin/common";

interface Row {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
}

function move<T>(list: T[], from: number, by: number): T[] {
  const to = from + by;
  if (to < 0 || to >= list.length) return list;
  const next = [...list];
  next.splice(to, 0, next.splice(from, 1)[0]!);
  return next;
}

/** One line of a list you can reorder: the item, then up, down and a show or hide button. */
function RowControls({
  row,
  index,
  count,
  onMove,
  end,
}: {
  row: Row;
  index: number;
  count: number;
  onMove: (by: number) => void;
  end: React.ReactNode;
}) {
  const Icon = row.icon;
  return (
    <li className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2">
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{row.label}</span>
        {row.hint && (
          <span className="block truncate text-xs text-muted-foreground">{row.hint}</span>
        )}
      </span>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Move ${row.label} up`}
        disabled={index === 0}
        onClick={() => onMove(-1)}
      >
        <ArrowUp aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Move ${row.label} down`}
        disabled={index === count - 1}
        onClick={() => onMove(1)}
      >
        <ArrowDown aria-hidden />
      </Button>
      {end}
    </li>
  );
}

/** Settings > Layout: what sits in the top bar, which sidebar links show, in what order, and
 * whether the sidebar shows words or only icons. Saved to the account. */
export function LayoutSettings() {
  const layout = useLayout();
  const order = useSidebarOrder();
  const labId = useCurrentLabId();
  const lab = useLabs().data?.find((l) => l.id === labId);

  const pages = useMemo(
    () =>
      navItems(labId, lab?.my_permissions, lab?.inventory_enabled).filter(
        (n) => n.to !== "/settings" && n.to !== "/help" && !n.to.endsWith("/notifications"),
      ),
    [labId, lab],
  );
  const catalog: Row[] = useMemo(
    () => [
      ...TOPBAR_BUILTIN,
      ...pages.map((n) => ({
        id: shortcutId(n.to),
        label: n.label,
        hint: "Shortcut to this page",
        icon: n.icon,
      })),
    ],
    [pages],
  );
  const shown = layout.topbar
    .map((id) => catalog.find((r) => r.id === id))
    .filter((r): r is Row => !!r);
  const available = catalog.filter((r) => !layout.topbar.includes(r.id));

  const main = applyOrder(
    pages.filter((p) => !p.admin),
    (p) => navKey(p.to),
    order.main,
  );
  const admin = applyOrder(
    pages.filter((p) => p.admin),
    (p) => navKey(p.to),
    order.admin,
  );
  const toggleHidden = (key: string) =>
    layout.setHidden(
      layout.hidden.includes(key)
        ? layout.hidden.filter((k) => k !== key)
        : [...layout.hidden, key],
    );

  const group = (title: string, items: typeof pages, set: (keys: string[]) => void) =>
    items.length > 0 && (
      <div className="grid gap-2">
        <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
          {title}
        </h3>
        <ul className="grid gap-2">
          {items.map((p, i) => {
            const key = navKey(p.to);
            const hidden = layout.hidden.includes(key);
            return (
              <RowControls
                key={p.to}
                row={{ id: key, label: p.label, icon: p.icon }}
                index={i}
                count={items.length}
                onMove={(by) =>
                  set(
                    move(
                      items.map((x) => navKey(x.to)),
                      i,
                      by,
                    ),
                  )
                }
                end={
                  <Button
                    variant={hidden ? "outline" : "ghost"}
                    size="icon"
                    aria-label={`${hidden ? "Show" : "Hide"} ${p.label} in the sidebar`}
                    aria-pressed={!hidden}
                    onClick={() => toggleHidden(key)}
                  >
                    {hidden ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
                  </Button>
                }
              />
            );
          })}
        </ul>
      </div>
    );

  return (
    <div className="grid gap-6">
      <Section
        title="Top bar"
        description="Choose what sits in the top bar and in what order. Add shortcuts to any page, or your pinned pages."
      >
        <ul className="grid gap-2" aria-label="Shown in the top bar">
          {shown.map((r, i) => (
            <RowControls
              key={r.id}
              row={r}
              index={i}
              count={shown.length}
              onMove={(by) =>
                layout.setTopbar(move(layout.topbar, layout.topbar.indexOf(r.id), by))
              }
              end={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${r.label} from the top bar`}
                  onClick={() => layout.setTopbar(layout.topbar.filter((id) => id !== r.id))}
                >
                  <X aria-hidden />
                </Button>
              }
            />
          ))}
          {shown.length === 0 && (
            <li className="text-sm text-muted-foreground">The top bar is empty.</li>
          )}
        </ul>
        {available.length > 0 && (
          <div className="grid gap-2">
            <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
              Add to the top bar
            </h3>
            <ul className="flex flex-wrap gap-2" aria-label="Available for the top bar">
              {available.map((r) => (
                <li key={r.id}>
                  <Button
                    variant="outline"
                    size="sm"
                    title={r.hint}
                    aria-label={`Add ${r.label} to the top bar`}
                    onClick={() => layout.setTopbar([...layout.topbar, r.id])}
                  >
                    <Plus aria-hidden />
                    <r.icon aria-hidden />
                    {r.label}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <Button variant="ghost" size="sm" onClick={layout.resetTopbar}>
            <RotateCcw aria-hidden /> Reset top bar
          </Button>
        </div>
      </Section>

      <Section
        title="Sidebar"
        description="Show or hide links, change their order, and shrink the sidebar to icons only."
      >
        <div
          role="radiogroup"
          aria-label="Sidebar size"
          className="flex w-fit gap-1 rounded-full border bg-card p-1"
        >
          {[
            { on: false, label: "Icons and words" },
            { on: true, label: "Icons only" },
          ].map((o) => (
            <Button
              key={o.label}
              role="radio"
              aria-checked={layout.compact === o.on}
              size="sm"
              variant={layout.compact === o.on ? "secondary" : "ghost"}
              onClick={() => layout.setCompact(o.on)}
            >
              {o.label}
            </Button>
          ))}
        </div>
        {group("Lab", main, order.setMain)}
        {group("Admin", admin, order.setAdmin)}
        <div>
          <Button variant="ghost" size="sm" onClick={layout.resetSidebar}>
            <RotateCcw aria-hidden /> Reset sidebar
          </Button>
        </div>
      </Section>
    </div>
  );
}
