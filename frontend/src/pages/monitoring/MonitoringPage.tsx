import { Thermometer } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSensors } from "@/hooks/monitoring";
import { useLab } from "@/hooks/workspace";
import type { Sensor } from "@/lib/api-types";
import { AlertBox, SensorDialog, StatusPill } from "./parts";
import { SensorChart, showValue } from "./SensorChart";

/** Freezers, fridges and incubators, each with its latest reading and the last 24 hours. */
export function MonitoringPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const on = !!lab?.inventory_enabled;
  const sensors = useSensors(labId, undefined, on);
  const canEdit = !!lab?.my_permissions.includes("manage_inventory");
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const add = canEdit ? <Button onClick={() => setAdding(true)}>Add a sensor</Button> : undefined;

  return (
    <>
      <PageHeader
        title="Monitoring"
        description="Freezers, fridges and incubators, watched day and night."
        actions={on && sensors.data?.length ? add : undefined}
      />
      {lab && !on && (
        <EmptyState
          title="Monitoring is turned off"
          description="It comes with inventory, which is off for this lab. A PI or lab admin can turn inventory on in Lab details."
        />
      )}
      {on && sensors.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      )}
      {on && sensors.data?.length === 0 && (
        <EmptyState
          icon={Thermometer}
          title="No sensors yet"
          description="Put a cheap Wi-Fi sensor in a freezer or incubator, and the right people get an email the moment it drifts out of range or goes quiet."
          why="A failed -80 can cost years of samples. Most fail at night or over a weekend."
          action={add}
        />
      )}
      {on && !!sensors.data?.length && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {sensors.data.map((s) => (
            <SensorCard
              key={s.id}
              labId={labId}
              sensor={s}
              canEdit={canEdit}
              end={sensors.dataUpdatedAt}
            />
          ))}
        </ul>
      )}
      {adding && (
        <SensorDialog
          labId={labId}
          onClose={() => setAdding(false)}
          onCreated={(id) => navigate(id)}
        />
      )}
    </>
  );
}

function SensorCard({
  labId,
  sensor: s,
  canEdit,
  end,
}: {
  labId: string;
  sensor: Sensor;
  canEdit: boolean;
  end: number;
}) {
  return (
    <li className="grid content-start gap-3 rounded-xl border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link to={s.id} className="block truncate font-medium underline-offset-2 hover:underline">
            {s.name}
          </Link>
          {s.item && <p className="truncate text-xs text-muted-foreground">{s.item.name}</p>}
        </div>
        <StatusPill status={s.status} />
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums">
          {showValue(s.last_value, s.unit_symbol)}
        </span>
        {s.last_at && (
          <span className="text-xs text-muted-foreground">
            <RelativeTime value={s.last_at} />
          </span>
        )}
      </div>
      <SensorChart
        points={s.series}
        low={s.low_limit}
        high={s.high_limit}
        symbol={s.unit_symbol}
        hours={24}
        end={end}
        compact
      />
      {s.status === "waiting" && (
        <p className="text-xs text-muted-foreground">
          No readings yet.{" "}
          <Link to={s.id} className="underline underline-offset-2">
            Set up the device
          </Link>
        </p>
      )}
      {s.alert && <AlertBox labId={labId} sensor={s} alert={s.alert} canEdit={canEdit} />}
    </li>
  );
}
