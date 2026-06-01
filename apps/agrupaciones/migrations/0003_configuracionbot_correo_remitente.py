from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agrupaciones", "0002_agrupacion_uuid_alter_configuracionbot_nombre_bot"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionbot",
            name="clave_app_remitente",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="configuracionbot",
            name="correo_remitente",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
