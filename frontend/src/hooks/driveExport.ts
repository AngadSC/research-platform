import { useMutation } from "@tanstack/react-query";
import { upload } from "@/lib/api";
import type { components } from "@/lib/api-schema";

export type DriveExported = components["schemas"]["DriveExportResult"];

/** Send a file made on the statistics page to the person's own Google Drive. Nothing is kept here. */
export function useDriveExport(labId: string, projectId: string) {
  return useMutation({
    mutationFn: ({
      file,
      name,
      participantData,
    }: {
      file: File;
      name: string;
      participantData: boolean;
    }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name);
      form.append("participant_data", String(participantData));
      return upload<DriveExported>(`/api/labs/${labId}/projects/${projectId}/drive-export/`, form);
    },
  });
}
