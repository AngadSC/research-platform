import { UserPlus } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { DataTable, HIDE_NARROW, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateInvite,
  useInvites,
  useLab,
  useMe,
  useMembers,
  useRemoveMember,
  useRevokeInvite,
  useUpdateInvite,
  useUpdateMember,
} from "@/hooks/workspace";
import { RoleName } from "@/components/shared/RoleName";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { ROLES, type Invite, type Membership, type Role } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";

const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function RoleSelect({
  value,
  onChange,
  label,
}: {
  value: Role;
  onChange: (r: Role) => void;
  label: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Role)}>
      <SelectTrigger
        aria-label={label}
        className="w-36"
        title={ROLES.find((r) => r.value === value)?.help}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value} hint={r.help}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function InviteForm({ labId }: { labId: string }) {
  const create = useCreateInvite(labId);
  const [role, setRole] = useState<Role>("member");
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const email = String(new FormData(form).get("email") ?? "").trim();
    if (!email) return setErrors({ fields: { email: "Enter an email address" } });
    if (!EMAIL.test(email))
      return setErrors({
        fields: { email: "Enter a valid email address, like name@university.edu" },
      });
    setErrors({ fields: {} });
    try {
      await create.mutateAsync({ email, role });
      toast.success(`Invitation sent to ${email}`);
      form.reset();
    } catch (err) {
      setErrors(formErrors(err, ["email", "role"]));
    }
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label="Invite someone"
      className="mb-8 grid gap-3 rounded-lg border p-6"
    >
      <h2 className="text-base font-semibold">Invite someone</h2>
      <div className="flex flex-wrap items-start gap-3">
        <div className="w-72">
          <FormField label="Email" error={errors.fields.email}>
            {(p) => <Input maxLength={254} {...p} name="email" type="email" autoComplete="off" />}
          </FormField>
        </div>
        <div className="w-40">
          <FormField label="Role" error={errors.fields.role}>
            {(p) => (
              <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                <SelectTrigger {...p}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r.value} value={r.value} hint={r.help}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
        </div>
        <Button type="submit" className="mt-[1.375rem]" disabled={create.isPending}>
          Send invitation
        </Button>
      </div>
      <FormError message={errors.form} />
    </form>
  );
}

function Confirm({
  open,
  title,
  description,
  action,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  action: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {description}
        </DialogDescription>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" onClick={onConfirm}>
            {action}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function MembersPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  // Controls come from the server's permission list, never from the role name.
  const canManage = lab?.my_permissions.includes("manage_members") ?? false;
  const members = useMembers(labId);
  const me = useMe().data;
  const invites = useInvites(labId, canManage);
  const update = useUpdateMember(labId);
  const remove = useRemoveMember(labId);
  const revoke = useRevokeInvite(labId);
  const updateInvite = useUpdateInvite(labId);
  const [removing, setRemoving] = useState<Membership | null>(null);
  const [revoking, setRevoking] = useState<Invite | null>(null);

  const memberCols: Column<Membership>[] = [
    {
      key: "name",
      header: "Name",
      cell: (m) => (
        <div className="flex items-center gap-3">
          <UserAvatar user={m.user} />
          <div className="min-w-0">
            <div className="font-medium">
              {m.user.display_name || m.user.email}
              {m.user.pronouns && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {m.user.pronouns}
                </span>
              )}
            </div>
            {m.user.display_name && (
              <div className="text-xs text-muted-foreground">{m.user.email}</div>
            )}
            {m.user.bio && <div className="mt-0.5 text-xs text-muted-foreground">{m.user.bio}</div>}
          </div>
        </div>
      ),
    },
    {
      key: "role",
      header: "Role",
      cell: (m) =>
        canManage ? (
          <RoleSelect
            label={`Role for ${m.user.email}`}
            value={m.role}
            onChange={(role) =>
              update.mutate(
                { id: m.id, role },
                { onSuccess: () => toast.success("Saved"), onError: fail },
              )
            }
          />
        ) : (
          <RoleName role={m.role} roles={ROLES} />
        ),
    },
    {
      key: "joined",
      header: "Joined",
      className: HIDE_NARROW,
      cell: (m) => <RelativeTime value={m.created_at} />,
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: (m: Membership) => {
        const mine = m.user.id === me?.id;
        const handover = (mine || canManage) && (
          <Button variant="ghost" size="sm" asChild>
            <Link
              to={`/labs/${labId}/members/${m.id}/handover`}
              aria-label={`${mine ? "My handover" : "Handover"} for ${m.user.email}`}
              title="Lists everything this person owns or leads, so it can be given to someone else when they leave."
            >
              {mine ? "My handover" : "Handover"}
            </Link>
          </Button>
        );
        return (
          <div className="flex justify-end gap-1">
            {handover}
            {canManage && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRemoving(m)}
                aria-label={`Remove ${m.user.email}`}
              >
                Remove
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  const inviteCols: Column<Invite>[] = [
    { key: "email", header: "Email", cell: (i) => i.email },
    {
      key: "role",
      header: "Role",
      cell: (i) => (
        <RoleSelect
          label={`Role for the invitation to ${i.email}`}
          value={i.role}
          onChange={(role) =>
            updateInvite.mutate(
              { id: i.id, role },
              { onSuccess: () => toast.success("Invitation role changed"), onError: fail },
            )
          }
        />
      ),
    },
    { key: "expires", header: "Expires", cell: (i) => <RelativeTime value={i.expires_at} /> },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: (i) => (
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Revoke invitation for ${i.email}`}
          onClick={() => setRevoking(i)}
        >
          Revoke
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Members" description={lab ? `People in ${lab.name}.` : undefined} />
      {canManage && <InviteForm labId={labId} />}
      <section className="mb-8 grid gap-3">
        <h2 className="text-base font-semibold">People</h2>
        <DataTable
          columns={memberCols}
          rows={members.data ?? []}
          getRowKey={(m) => m.id}
          loading={members.isLoading || !lab}
          empty={
            <EmptyState
              title="No members yet"
              description="People you add to this lab will appear here."
            />
          }
        />
      </section>
      {canManage && (
        <section className="grid gap-3">
          <h2 className="text-base font-semibold">Pending invitations</h2>
          <DataTable
            columns={inviteCols}
            rows={invites.data ?? []}
            getRowKey={(i) => i.id}
            loading={invites.isLoading}
            empty={
              <EmptyState
                icon={UserPlus}
                title="No pending invitations"
                description="Invitations you send stay here until they are accepted or expire."
              />
            }
          />
        </section>
      )}
      <Confirm
        open={!!revoking}
        title={`Revoke the invitation to ${revoking?.email ?? ""}?`}
        description="The link in their email will stop working. You can invite them again later."
        action="Revoke"
        onClose={() => setRevoking(null)}
        onConfirm={() => {
          if (!revoking) return;
          revoke.mutate(revoking.id, {
            onSuccess: () => toast.success("Invitation revoked"),
            onError: fail,
            onSettled: () => setRevoking(null),
          });
        }}
      />
      <Confirm
        open={!!removing}
        title={`Remove ${removing?.user.display_name || removing?.user.email || ""}?`}
        description="They will lose access to this lab and its projects. You can invite them again later."
        action="Remove"
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (!removing) return;
          remove.mutate(removing.id, {
            onSuccess: () => toast.success("Member removed"),
            onError: fail,
            onSettled: () => setRemoving(null),
          });
        }}
      />
    </>
  );
}
