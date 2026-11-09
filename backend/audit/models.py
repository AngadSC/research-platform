import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class AuditImmutableError(Exception):
    """AuditEvent rows are append-only (D23)."""


class AuditAction(models.TextChoices):
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    AUTH_MFA_ENABLED = "auth.mfa_enabled"
    AUTH_MFA_DISABLED = "auth.mfa_disabled"
    LAB_CREATED = "lab.created"
    LAB_UPDATED = "lab.updated"
    MEMBERSHIP_INVITED = "membership.invited"
    MEMBERSHIP_INVITE_REVOKED = "membership.invite_revoked"
    MEMBERSHIP_INVITE_ACCEPTED = "membership.invite_accepted"
    MEMBERSHIP_ROLE_CHANGED = "membership.role_changed"
    MEMBERSHIP_REMOVED = "membership.removed"
    PROJECT_MEMBERSHIP_ADDED = "project_membership.added"
    PROJECT_MEMBERSHIP_ROLE_CHANGED = "project_membership.role_changed"
    PROJECT_MEMBERSHIP_REMOVED = "project_membership.removed"
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    PROJECT_EXPORTED = "project.exported"
    DOCUMENT_VIEWED = "document.viewed"
    DOCUMENT_RESTORED = "document.restored"
    DOCUMENT_DELETED = "document.deleted"
    ATTACHMENT_UPLOADED = "attachment.uploaded"
    ATTACHMENT_DOWNLOADED = "attachment.downloaded"
    ATTACHMENT_DELETED = "attachment.deleted"
    TASK_DELETED = "task.deleted"
    TASK_POST_DELETED = "task_post.deleted"
    DEADLINE_DELETED = "deadline.deleted"
    DATASET_CREATED = "dataset.created"
    DATASET_UPDATED = "dataset.updated"
    DATASET_DELETED = "dataset.deleted"
    ANALYSIS_CREATED = "analysis.created"
    ANALYSIS_UPDATED = "analysis.updated"
    ANALYSIS_DELETED = "analysis.deleted"
    RESULT_CREATED = "result.created"
    RESULT_UPDATED = "result.updated"
    RESULT_DELETED = "result.deleted"
    DECISION_CREATED = "decision.created"
    DECISION_UPDATED = "decision.updated"
    DECISION_DELETED = "decision.deleted"
    MANUSCRIPT_CREATED = "manuscript.created"
    MANUSCRIPT_UPDATED = "manuscript.updated"
    MANUSCRIPT_DELETED = "manuscript.deleted"
    ETHICS_APPROVAL_CREATED = "ethics_approval.created"
    ETHICS_APPROVAL_UPDATED = "ethics_approval.updated"
    ETHICS_APPROVAL_LINKS_CHANGED = "ethics_approval.links_changed"
    ETHICS_APPROVAL_DELETED = "ethics_approval.deleted"
    RETENTION_CHANGED = "retention.changed"
    AUDIT_LOG_VIEWED = "audit_log.viewed"
    HANDOVER_GENERATED = "handover.generated"
    # Run 2
    TASK_UNASSIGNED = "task.unassigned"
    AUTH_SOCIAL_CONNECTED = "auth.social_connected"
    AUTH_SOCIAL_DISCONNECTED = "auth.social_disconnected"
    AUTH_EMAIL_ADDED = "auth.email_added"
    AUTH_EMAIL_REMOVED = "auth.email_removed"
    INTEGRATION_CONNECTED = "integration.connected"
    INTEGRATION_DISCONNECTED = "integration.disconnected"
    INTEGRATION_REVOKED = "integration.revoked"
    INTEGRATION_REFRESH_FAILED = "integration.refresh_failed"
    INTEGRATION_PICKER_TOKEN = "integration.picker_token_issued"
    EXTERNAL_LINK_CREATED = "external_link.created"
    EXTERNAL_LINK_REMOVED = "external_link.removed"
    EXTERNAL_LINK_CHANGE_ACCEPTED = "external_link.change_accepted"
    CHAT_MESSAGE_DELETED = "chat_message.deleted"
    # Run 3 (integrations framework, D85)
    INTEGRATION_SEARCHED = "integration.searched"
    # Run 4 (admin area, D146-D151)
    INVENTORY_ITEM_CREATED = "inventory_item.created"
    INVENTORY_ITEM_UPDATED = "inventory_item.updated"
    INVENTORY_ITEM_DELETED = "inventory_item.deleted"
    INVENTORY_EXPORTED = "inventory.exported"
    INVENTORY_ORDER_CREATED = "inventory_order.created"
    INVENTORY_ORDER_UPDATED = "inventory_order.updated"
    LAB_EVENT_CREATED = "lab_event.created"
    LAB_EVENT_UPDATED = "lab_event.updated"
    LAB_EVENT_DELETED = "lab_event.deleted"
    ONBOARDING_ITEM_CREATED = "onboarding_item.created"
    ONBOARDING_ITEM_UPDATED = "onboarding_item.updated"
    ONBOARDING_ITEM_DELETED = "onboarding_item.deleted"
    ONBOARDING_COMPLETION_CHANGED = "onboarding.completion_changed"
    INSTITUTION_RESOURCE_CREATED = "institution_resource.created"
    INSTITUTION_RESOURCE_UPDATED = "institution_resource.updated"
    INSTITUTION_RESOURCE_DELETED = "institution_resource.deleted"
    # Run 4 (project workflow, D132-D139)
    FUNDING_CREATED = "funding.created"
    FUNDING_UPDATED = "funding.updated"
    FUNDING_DELETED = "funding.deleted"
    REVIEW_ITEM_CREATED = "review_item.created"
    REVIEW_ITEM_UPDATED = "review_item.updated"
    REVIEW_ITEM_DELETED = "review_item.deleted"
    RECRUITMENT_ENTRY_CREATED = "recruitment_entry.created"
    RECRUITMENT_ENTRY_UPDATED = "recruitment_entry.updated"
    RECRUITMENT_ENTRY_DELETED = "recruitment_entry.deleted"
    RECRUITMENT_PLAN_UPDATED = "recruitment_plan.updated"
    # Run 5 (AI access and MCP, D160-D169)
    AI_ACCESS_GRANTED = "ai_access.granted"
    AI_ACCESS_REVOKED = "ai_access.revoked"
    AI_TOOL_WRITE = "ai_tool.write"
    # Run 5 (in-app assistant, D187-D192): a person's own provider key; the key never appears
    AI_KEY_SAVED = "ai_key.saved"
    AI_KEY_REMOVED = "ai_key.removed"
    # Run 5 (training, D175-D179)
    TRAINING_REQUIREMENT_CREATED = "training_requirement.created"
    TRAINING_REQUIREMENT_UPDATED = "training_requirement.updated"
    TRAINING_REQUIREMENT_DELETED = "training_requirement.deleted"
    TRAINING_RECORD_CREATED = "training_record.created"
    TRAINING_RECORD_UPDATED = "training_record.updated"
    TRAINING_RECORD_VERIFIED = "training_record.verified"
    TRAINING_RECORD_DELETED = "training_record.deleted"
    # Run 5 (data management plan, D180-D186)
    DMP_CREATED = "dmp.created"
    DMP_UPDATED = "dmp.updated"
    DMP_APPROVED = "dmp.approved"
    DMP_DELETED = "dmp.deleted"
    # Paper library
    PAPER_DELETED = "paper.deleted"
    PAPER_NOTE_DELETED = "paper_note.deleted"


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditImmutableError("AuditEvent is append-only")

    def delete(self):
        raise AuditImmutableError("AuditEvent is append-only")

    def bulk_update(self, *args, **kwargs):
        raise AuditImmutableError("AuditEvent is append-only")

    delete.queryset_only = True


class AuditEvent(models.Model):
    """Not lab-scoped: `lab` is null only for auth.* events. Targets are plain UUIDs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(db_default=Now())
    lab = models.ForeignKey(
        "labs.Lab", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    actor_label = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=64, choices=AuditAction.choices)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    target_repr = models.CharField(max_length=200, blank=True)
    project_id = models.UUIDField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["lab", "-occurred_at"], name="audit_lab_time_idx"),
            models.Index(fields=["lab", "target_type", "target_id"], name="audit_lab_target_idx"),
            models.Index(fields=["actor", "occurred_at"], name="audit_actor_time_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.target_repr}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditImmutableError("AuditEvent is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmutableError("AuditEvent is append-only")
