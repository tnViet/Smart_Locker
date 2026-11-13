from django.db import migrations
from django.utils import timezone


def create_initial_data(apps, schema_editor):
    FeeRule = apps.get_model("lockers", "FeeRule")
    Group = apps.get_model("auth", "Group")

    FeeRule.objects.get_or_create(
        id=1,
        defaults={
            "free_min": 5,
            "block_min": 60,
            "block_fee": 2000,
            "updated_at": timezone.now(),
        },
    )
    Group.objects.get_or_create(name="viewer")
    Group.objects.get_or_create(name="admin")


def remove_initial_data(apps, schema_editor):
    FeeRule = apps.get_model("lockers", "FeeRule")
    Group = apps.get_model("auth", "Group")

    FeeRule.objects.filter(id=1).delete()
    Group.objects.filter(name__in=["viewer", "admin"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("lockers", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_initial_data, remove_initial_data),
    ]
