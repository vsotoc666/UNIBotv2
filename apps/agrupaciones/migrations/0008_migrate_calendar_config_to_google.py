from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agrupaciones", "0007_configuracionbot_notion_calendar_db_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="configuracionbot",
            name="notion_calendar_enabled",
        ),
        migrations.RemoveField(
            model_name="configuracionbot",
            name="notion_calendar_url",
        ),
        migrations.RemoveField(
            model_name="configuracionbot",
            name="notion_calendar_database_id",
        ),
        migrations.RemoveField(
            model_name="configuracionbot",
            name="notion_calendar_title_property",
        ),
        migrations.RemoveField(
            model_name="configuracionbot",
            name="notion_calendar_date_property",
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="google_calendar_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="google_calendar_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
