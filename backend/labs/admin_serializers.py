"""Input and output serializers for the admin area (D146-D151). Inputs are plain (D33)."""

from decimal import Decimal
from urllib.parse import urlsplit

from rest_framework import serializers

from core.models import User
from core.serializers import UserSerializer, no_control_chars
from instrument_parsers import SOFTWARE_CHOICES
from labs.models import (
    InstitutionResource,
    InventoryCategory,
    InventoryItem,
    InventoryOrder,
    InventoryStatus,
    OnboardingItem,
    OnboardingKind,
    OrderStatus,
    ResourceCategory,
)


def https_url(value):
    """https only, a host, no embedded credentials (D149). Applies to every user-supplied link."""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise serializers.ValidationError("Enter a web address starting with https://")
    no_control_chars(value)
    return value


def web_url(value):
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise serializers.ValidationError("Enter a web address starting with http:// or https://")
    return value


class LabDetailsInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    institution_name = serializers.CharField(max_length=200, validators=[no_control_chars])
    department = serializers.CharField(
        max_length=200, allow_blank=True, validators=[no_control_chars]
    )
    description = serializers.CharField(max_length=5000, allow_blank=True)
    address = serializers.CharField(max_length=1000, allow_blank=True)
    contact_email = serializers.EmailField(allow_blank=True)
    website = serializers.CharField(max_length=300, allow_blank=True)
    inventory_enabled = serializers.BooleanField(required=False)  # D227

    def validate_website(self, value):
        return web_url(value) if value else value


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstitutionResource
        fields = ["id", "category", "title", "url", "description", "order"]
        read_only_fields = ["id"]


class ResourceInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=ResourceCategory.choices)
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    url = serializers.CharField(max_length=500, validators=[https_url])
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    order = serializers.IntegerField(min_value=0, max_value=100000, required=False)


class StartersLoadedSerializer(serializers.Serializer):
    added = serializers.IntegerField()
    institution = serializers.CharField()
    curated_institution = serializers.CharField(allow_null=True)


class OnboardingItemSerializer(serializers.ModelSerializer):
    completed_user_ids = serializers.SerializerMethodField()
    # D179: a linked training counts as done for anyone whose current record is not expired
    training_requirement = serializers.UUIDField(source="training_requirement_id", allow_null=True)
    training_requirement_name = serializers.SerializerMethodField()
    training_done_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingItem
        fields = [
            "id",
            "kind",
            "title",
            "description",
            "url",
            "required",
            "order",
            "completed_user_ids",
            "training_requirement",
            "training_requirement_name",
            "training_done_user_ids",
        ]
        read_only_fields = fields

    def get_completed_user_ids(self, item) -> list[str]:
        return sorted(str(c.user_id) for c in item.completions.all())

    def get_training_requirement_name(self, item) -> str:
        return item.training_requirement.name if item.training_requirement else ""

    def get_training_done_user_ids(self, item) -> list[str]:
        if item.training_requirement is None:
            return []
        from training.services import done_user_ids

        return done_user_ids(item.lab, item.training_requirement)


class MyOnboardingSerializer(serializers.ModelSerializer):
    """One checklist line as the signed-in member sees it: only their own tick, nobody else's."""

    done = serializers.SerializerMethodField()
    by_training = serializers.SerializerMethodField(
        help_text="Ticked by a current training record, so it cannot be ticked by hand."
    )
    training_linked = serializers.SerializerMethodField(
        help_text="Ticks itself from training records, so it cannot be ticked by hand."
    )
    training_requirement_name = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingItem
        fields = [
            "id",
            "title",
            "description",
            "url",
            "required",
            "done",
            "by_training",
            "training_linked",
            "training_requirement_name",
        ]
        read_only_fields = fields

    def _me(self):
        return self.context["request"].user

    def get_by_training(self, item) -> bool:
        if item.training_requirement is None:
            return False
        from training.services import done_user_ids

        return str(self._me().pk) in done_user_ids(item.lab, item.training_requirement)

    def get_training_linked(self, item) -> bool:
        return item.training_requirement_id is not None

    def get_done(self, item) -> bool:
        mine = any(c.user_id == self._me().pk for c in item.completions.all())
        return mine or self.get_by_training(item)

    def get_training_requirement_name(self, item) -> str:
        return item.training_requirement.name if item.training_requirement else ""


class MyOnboardingTickSerializer(serializers.Serializer):
    done = serializers.BooleanField()


class OnboardingItemInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=OnboardingKind.choices)
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    url = serializers.CharField(max_length=500, allow_blank=True, required=False)
    required = serializers.BooleanField(required=False)
    order = serializers.IntegerField(min_value=0, max_value=100000, required=False)
    training_requirement = serializers.UUIDField(allow_null=True, required=False)  # D179

    def validate_url(self, value):
        return https_url(value) if value else value


class CompletionInputSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    done = serializers.BooleanField()


class InventorySerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    low = serializers.SerializerMethodField(help_text="Stock is at or below its alert level.")

    def get_low(self, item) -> bool:
        return item.low_stock_at is not None and item.quantity <= item.low_stock_at

    weeks_left = serializers.SerializerMethodField(
        help_text="About how many weeks the stock lasts at the last 8 weeks' use; null with "
        "fewer than 2 uses in that time."
    )

    def get_weeks_left(self, item) -> int | None:
        taken = getattr(item, "recent_taken", None)
        if (getattr(item, "recent_uses", None) or 0) < 2 or not taken:
            return None
        return round(float(item.quantity) / (float(taken) / 8))

    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "name",
            "category",
            "location",
            "quantity",
            "unit",
            "low_stock_at",
            "low",
            "weeks_left",
            "owner",
            "serial_number",
            "purchase_date",
            "due_date",
            "status",
            "notes",
            "instrument_software",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InventoryInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    category = serializers.ChoiceField(choices=InventoryCategory.choices)
    location = serializers.CharField(max_length=200, allow_blank=True, required=False)
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, required=False
    )
    unit = serializers.CharField(max_length=32, allow_blank=True, required=False)
    low_stock_at = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, required=False, allow_null=True
    )
    owner = serializers.UUIDField(allow_null=True, required=False)  # resolved in the service
    serial_number = serializers.CharField(max_length=100, allow_blank=True, required=False)
    purchase_date = serializers.DateField(allow_null=True, required=False)
    due_date = serializers.DateField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=InventoryStatus.choices, required=False)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    instrument_software = serializers.ChoiceField(
        choices=SOFTWARE_CHOICES, allow_blank=True, required=False
    )


class InventoryImportInputSerializer(serializers.Serializer):
    file = serializers.FileField()
    commit = serializers.BooleanField(required=False, default=False)  # false means preview only


class InventoryImportRowSerializer(serializers.Serializer):
    row = serializers.IntegerField(help_text="The line in the file (the header is line 1).")
    name = serializers.CharField()
    category = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField()
    errors = serializers.DictField(child=serializers.CharField())
    warning = serializers.CharField(help_text="Worth checking, but does not stop the import.")


class InventoryImportResultSerializer(serializers.Serializer):
    rows = InventoryImportRowSerializer(many=True)
    valid = serializers.IntegerField()
    invalid = serializers.IntegerField()
    imported = serializers.IntegerField(help_text="Items added; 0 for a preview.")
    ignored_columns = serializers.ListField(child=serializers.CharField())


class InventoryOrderSerializer(serializers.ModelSerializer):
    requested_by = UserSerializer(read_only=True)
    item = serializers.UUIDField(source="item_id", allow_null=True)
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryOrder
        fields = [
            "id",
            "item",
            "item_name",
            "name",
            "vendor",
            "catalog_number",
            "url",
            "quantity",
            "unit",
            "status",
            "notes",
            "requested_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_item_name(self, order) -> str:
        return order.item.name if order.item else ""


class InventoryOrderInputSerializer(serializers.Serializer):
    item = serializers.UUIDField(allow_null=True, required=False)  # resolved in the service
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    vendor = serializers.CharField(
        max_length=200, allow_blank=True, required=False, validators=[no_control_chars]
    )
    catalog_number = serializers.CharField(
        max_length=100, allow_blank=True, required=False, validators=[no_control_chars]
    )
    url = serializers.CharField(max_length=500, allow_blank=True, required=False)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    unit = serializers.CharField(max_length=32, allow_blank=True, required=False)
    status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)

    def validate_url(self, value):
        return https_url(value) if value else value
