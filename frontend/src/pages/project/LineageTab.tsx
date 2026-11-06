import { List, Network } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { LineageDetail } from "@/components/lineage/LineageDetail";
import { LineageGraph } from "@/components/lineage/LineageGraph";
import { LineageList } from "@/components/lineage/LineageList";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLineage } from "@/hooks/lineage";
import { formErrors } from "@/lib/forms";
import { indexLineage } from "@/lib/lineage";
import type { ProjectTabProps } from "@/pages/ProjectPage";

export default function LineageTab({ labId, projectId }: ProjectTabProps) {
  const { data, error, isLoading, refetch } = useLineage(labId, projectId);
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(() => params.get("focus"));
  const [listView, setListView] = useState(false);
  const ix = useMemo(() => (data ? indexLineage(data) : null), [data]);
  const select = useCallback((id: string) => setSelectedId(id), []);

  if (isLoading)
    return (
      <div aria-busy="true" aria-label="Loading lineage" className="grid gap-4">
        <Skeleton className="h-6 w-56" />
        <div className="grid h-80 grid-cols-4 gap-6 rounded-lg border p-6">
          {[3, 2, 2, 1].map((rows, c) => (
            <div key={c} className="grid content-start gap-4">
              <Skeleton className="h-3 w-20" />
              {Array.from({ length: rows }, (_, r) => (
                <Skeleton key={r} className="h-14" />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  if (error || !data || !ix)
    return (
      <div className="grid justify-items-start gap-3">
        <FormError
          message={formErrors(error, []).form ?? "We couldn't load the lineage. Please try again."}
        />
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  if (!data.nodes.length)
    return (
      <EmptyState
        icon={Network}
        title="Add a dataset to start tracing your work"
        description="Once you add datasets, analyses, results and manuscripts, you can follow any result back to the exact data and code behind it."
        action={
          <Button asChild>
            <Link to={`/labs/${labId}/projects/${projectId}/workflow/data`}>Add a dataset</Link>
          </Button>
        }
      />
    );

  return (
    <div className="grid gap-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Lineage</h2>
          <p className="text-sm text-muted-foreground">
            Follow any result back to its data and code. Select an item for details.
          </p>
        </div>
        <Button variant="outline" aria-pressed={listView} onClick={() => setListView((v) => !v)}>
          <List className="size-4" aria-hidden />
          List view
        </Button>
      </div>
      {listView ? (
        <LineageList data={data} onSelect={select} />
      ) : (
        <div className="h-[calc(100vh-20rem)] min-h-[420px] overflow-hidden rounded-lg border bg-muted/30">
          <LineageGraph data={data} selectedId={selectedId} onSelect={select} />
        </div>
      )}
      <LineageDetail
        ix={ix}
        node={selectedId ? (ix.byId.get(selectedId) ?? null) : null}
        labId={labId}
        projectId={projectId}
        onSelect={select}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
