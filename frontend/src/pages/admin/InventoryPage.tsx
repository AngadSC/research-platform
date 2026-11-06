import { useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { useLab } from "@/hooks/workspace";
import { InventorySection } from "./InventorySection";

/** Inventory for every lab member; editing needs manage_inventory (D147). */
export function InventoryPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  return (
    <>
      <PageHeader title="Inventory" description={lab ? `What ${lab.name} owns.` : undefined} />
      {lab && (
        <InventorySection labId={labId} canEdit={lab.my_permissions.includes("manage_inventory")} />
      )}
    </>
  );
}
