from collections import Counter, defaultdict

from django.db import migrations, models

PALETTE = (
    "blue",
    "orange",
    "green",
    "pink",
    "teal",
    "yellow",
    "violet",
    "red",
    "lime",
    "brown",
)


def assign_colors(apps, schema_editor):
    """Each lab's live projects, oldest first, take its least used colour."""
    Project = apps.get_model("projects", "Project")
    used = defaultdict(Counter)
    projects = list(Project.objects.filter(deleted_at__isnull=True).order_by("created_at"))
    for project in projects:
        counts = used[project.lab_id]
        project.color = min(PALETTE, key=lambda color: counts[color])
        counts[project.color] += 1
    Project.objects.bulk_update(projects, ["color"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0006_chatreadstate"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="color",
            field=models.CharField(
                choices=[
                    ("blue", "Blue"),
                    ("orange", "Orange"),
                    ("green", "Green"),
                    ("pink", "Pink"),
                    ("teal", "Teal"),
                    ("yellow", "Yellow"),
                    ("violet", "Violet"),
                    ("red", "Red"),
                    ("lime", "Lime"),
                    ("brown", "Brown"),
                ],
                default="blue",
                max_length=16,
            ),
        ),
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
