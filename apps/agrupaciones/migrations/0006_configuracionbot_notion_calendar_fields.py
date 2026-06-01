from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agrupaciones", "0005_configuracionbot_notion_oauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_calendar_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_calendar_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
