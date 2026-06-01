from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agrupaciones", "0003_configuracionbot_correo_remitente"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="google_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="google_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="google_refresh_token",
            field=models.TextField(blank=True, default=""),
        ),
    ]
