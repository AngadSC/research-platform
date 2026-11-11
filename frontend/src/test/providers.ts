/** Fake provider metadata, one per auth type, in the shape of GET .../integrations/providers/. */
const base = {
  category: "storage",
  metadata_only: true,
  scopes: [],
  configured: true,
  public_config: {},
  link_targets: ["project", "dataset"],
  link_methods: [],
  needs_instance_url: false,
  connect_fields: [],
  external_id_pattern: "",
  url_pattern: "",
  link_hosts: [],
  can_check: false,
  bundle: [] as string[],
  bundle_label: "",
  account: null,
};
const active = { id: "acc", status: "active", external_email: "ada@x.test", instance_url: "" };

export const OAUTH = {
  ...base,
  name: "dropbox",
  label: "Dropbox",
  auth_type: "oauth2",
  icon: "dropbox",
  link_methods: ["search"],
};
export const KEYED = {
  ...base,
  name: "zotero",
  label: "Zotero",
  auth_type: "api_key",
  category: "references",
  icon: "zotero",
  link_methods: ["search"],
  needs_instance_url: true,
  connect_fields: [
    {
      name: "api_key",
      label: "API key",
      help_text: "From your account settings.",
      required: true,
      secret: true,
    },
    {
      name: "instance_url",
      label: "Server address",
      help_text: "Only for self-hosted servers.",
      required: false,
      secret: false,
    },
  ],
};
export const LINK_ONLY = {
  ...base,
  name: "overleaf",
  label: "Overleaf",
  auth_type: "link_only",
  category: "writing",
  icon: "overleaf",
  link_methods: ["paste_url"],
  url_pattern: "https://www\\.overleaf\\.com/project/(?P<id>[0-9a-f]{24})",
  link_hosts: ["www.overleaf.com"],
};
export const PUBLIC = {
  ...base,
  name: "zenodo",
  label: "Zenodo",
  auth_type: "public",
  category: "repository",
  icon: "zenodo",
  link_targets: ["dataset", "result"],
  link_methods: ["paste_url"],
  url_pattern: "https://zenodo\\.org/records/(?P<id>\\d+)",
};
export const connected = <T extends object>(p: T) => ({ ...p, account: active });
