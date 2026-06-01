from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agrupaciones", "0006_configuracionbot_notion_calendar_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_calendar_database_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_calendar_title_property",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_calendar_date_property",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
