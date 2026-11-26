"""Wet lab sample registry (plasmids, strains, primers...) and where their tubes are.
Lab-level like inventory (D147): every lab member reads; `manage_samples` edits; everything is
off while the lab has inventory turned off (D227)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel


class SampleKind(models.TextChoices):
    PLASMID = "plasmid", "Plasmid"
    STRAIN = "strain", "Strain"
    PRIMER = "primer", "Primer"
    CONSTRUCT = "construct", "Construct"
    CELL_LINE = "cell_line", "Cell line"
    ANTIBODY = "antibody", "Antibody"
    PROTEIN = "protein", "Protein or enzyme batch"
    OTHER = "other", "Other"


# The suggested code is the prefix and the next number: P0012.
CODE_PREFIX = {
    SampleKind.PLASMID: "P",
    SampleKind.STRAIN: "S",
    SampleKind.PRIMER: "PR",
    SampleKind.CONSTRUCT: "C",
    SampleKind.CELL_LINE: "CL",
    SampleKind.ANTIBODY: "AB",
    SampleKind.PROTEIN: "E",
    SampleKind.OTHER: "X",
}


class SampleStatus(models.TextChoices):
    IN_USE = "in_use", "In use"
    VERIFIED = "verified", "Verified"
    ARCHIVED = "archived", "Archived"


class Sample(LabScopedModel):
    """One registry entry. Kind-specific fields are plain columns; the form shows the ones that
    fit the kind. Deleting is soft, so a code is never silently reused for something else."""

    permission_domain = "lab"

    kind = models.CharField(max_length=16, choices=SampleKind.choices)
    code = models.CharField(max_length=32)  # upper case, unique in the lab among live entries
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    status = models.CharField(
        max_length=16, choices=SampleStatus.choices, default=SampleStatus.IN_USE
    )
    # plasmid, construct
    backbone = models.CharField(max_length=200, blank=True)
    insert = models.CharField(max_length=200, blank=True)
    resistance = models.CharField(max_length=200, blank=True)
    tag = models.CharField(max_length=200, blank=True)
    # strain, cell line, antibody (host)
    species = models.CharField(max_length=200, blank=True)
    genotype = models.CharField(max_length=500, blank=True)
    # primer, 5' to 3'
    sequence = models.CharField(max_length=500, blank=True)
    # protein or enzyme batch, antibody
    concentration = models.CharField(max_length=64, blank=True)
    buffer = models.CharField(max_length=200, blank=True)
    made_on = models.DateField(null=True, blank=True)

    parents = models.ManyToManyField("self", symmetrical=False, related_name="children", blank=True)
    projects = models.ManyToManyField("projects.Project", related_name="+", blank=True)
    # Existing project files (a map in the project's files). Shown only to people who can see
    # them there; uploads made on the sample itself are `attachments` (Attachment.sample).
    linked_files = models.ManyToManyField("documents.Attachment", related_name="+", blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(deleted_at__isnull=True)

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "kind"], name="sample_lab_kind_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["lab", "code"],
                condition=Q(deleted_at__isnull=True),
                name="sample_code_unique",
            )
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class StorageKind(models.TextChoices):
    FREEZER = "freezer", "Freezer"
    FRIDGE = "fridge", "Fridge"
    LN2 = "ln2", "Liquid nitrogen"
    ROOM = "room", "Room temperature"


class StorageUnit(LabScopedModel):
    """A freezer, fridge, LN2 dewar or shelf, optionally the inventory item it is."""

    permission_domain = "lab"
    lab_parents = ("equipment",)

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=16, choices=StorageKind.choices, default=StorageKind.FREEZER)
    temperature = models.CharField(max_length=32, blank=True)  # "-80 °C"
    location = models.CharField(max_length=200, blank=True)
    equipment = models.ForeignKey(
        "labs.InventoryItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return self.name


MAX_SIDE = 26  # rows are lettered A to Z


class StorageBox(LabScopedModel):
    permission_domain = "lab"
    lab_parents = ("unit",)

    unit = models.ForeignKey(StorageUnit, on_delete=models.PROTECT, related_name="boxes")
    name = models.CharField(max_length=100)
    rows = models.PositiveSmallIntegerField(default=9)
    cols = models.PositiveSmallIntegerField(default=9)
    shelf = models.CharField(max_length=100, blank=True)  # "Shelf 2, rack B"

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(rows__gte=1, rows__lte=MAX_SIDE, cols__gte=1, cols__lte=MAX_SIDE),
                name="box_size_range",
            )
        ]

    def __str__(self):
        return self.name


def position_label(row: int, col: int) -> str:
    return f"{chr(64 + row)}{col}"


class Tube(LabScopedModel):
    """One tube of a sample at one position in a box. `owner` is who holds it."""

    permission_domain = "lab"
    lab_parents = ("box", "sample")

    box = models.ForeignKey(StorageBox, on_delete=models.PROTECT, related_name="tubes")
    row = models.PositiveSmallIntegerField()  # 1 is A
    col = models.PositiveSmallIntegerField()  # 1-based
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="tubes")
    label = models.CharField(max_length=100, blank=True)
    amount = models.CharField(max_length=64, blank=True)  # "50 µL", "1 mL glycerol stock"
    stored_on = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["box", "row", "col"], name="tube_one_per_position")
        ]

    @property
    def position(self) -> str:
        return position_label(self.row, self.col)

    def __str__(self):
        return f"{self.sample.code} at {self.box.name} {self.position}"
