import { useState } from "react";
import { useParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useLab } from "@/hooks/workspace";
import type { InventoryItem } from "@/lib/api-types";
import { InventorySection } from "./InventorySection";
import { OrdersSection } from "./OrdersSection";

/** Inventory for every lab member; editing needs manage_inventory (D147). */
export function InventoryPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const [reorder, setReorder] = useState<InventoryItem | null>(null);
  const canEdit = !!lab?.my_permissions.includes("manage_inventory");
  return (
    <>
      <PageHeader title="Inventory" description={lab ? `What ${lab.name} owns.` : undefined} />
      {lab && !lab.inventory_enabled && (
        <EmptyState
          title="Inventory is turned off"
          description="This lab is set up as a dry lab. A PI or lab admin can turn inventory on in Lab details."
        />
      )}
      {lab?.inventory_enabled && (
        <div className="grid gap-6">
          <InventorySection labId={labId} canEdit={canEdit} onReorder={setReorder} />
          <OrdersSection
            labId={labId}
            canEdit={canEdit}
            reorder={reorder}
            onReorderClose={() => setReorder(null)}
          />
        </div>
      )}
    </>
  );
}
