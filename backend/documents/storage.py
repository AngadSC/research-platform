"""The S3 storage for lab files (ARCHITECTURE section 8, D123)."""

from storages.backends.s3 import S3Storage


class LabFilesS3Storage(S3Storage):
    """Every object is written as an opaque forced download: `application/octet-stream`,
    `Content-Disposition: attachment`, `Cache-Control: private, no-store`. A presigned URL's
    `response-*` overrides still set the real type and filename, but a provider that ignores
    them can no longer serve an uploaded file as a page on the bucket origin. (The upload's
    declared type is deliberately not used: it is client input.)"""

    def get_object_parameters(self, name):
        return {
            **super().get_object_parameters(name),
            "ContentType": "application/octet-stream",
            "ContentDisposition": "attachment",
            "CacheControl": "private, no-store",
        }
