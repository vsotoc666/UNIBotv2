from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agrupaciones", "0008_migrate_calendar_config_to_google"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="clipup_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="clipup_api_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="clipup_list_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="clipup_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
