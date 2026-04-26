from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agrupaciones", "0004_configuracionbot_google_oauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_access_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_workspace_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="notion_workspace_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
