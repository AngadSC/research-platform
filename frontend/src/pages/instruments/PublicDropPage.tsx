import { useParams } from "react-router";
import { DropZone } from "@/components/instruments/DropZone";
import { Skeleton } from "@/components/ui/skeleton";
import { publicDropFile, serverDetail, usePublicDrop } from "@/hooks/instruments";

/** `/drop/<token>`: a drop link on a shared instrument PC or at a core facility. No sign-in;
 * it shows only the instrument and project names, and it can only send files. */
export function PublicDropPage() {
  const { token = "" } = useParams();
  const info = usePublicDrop(token);

  if (info.isLoading)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-full" />
      </div>
    );
  if (!info.data)
    return (
      <>
        <h1 className="mb-2 text-2xl font-semibold tracking-tight">This link can't be used</h1>
        <p className="text-sm text-muted-foreground">
          {serverDetail(info.error) ??
            "It may have expired or been turned off. Ask the person who gave it to you for a new one."}
        </p>
      </>
    );
  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Send files from {info.data.instrument}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Into the project {info.data.project}. You will not see the project&apos;s other files.
        </p>
      </div>
      <DropZone
        send={(file, participant, onProgress) =>
          publicDropFile(token, file, participant, onProgress)
        }
      />
    </div>
  );
}
