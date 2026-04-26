from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("eventos", "0004_fix_recordatorio_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="inscripcion",
            name="confirmacion_email_enviada",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="inscripcion",
            name="confirmacion_email_enviada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
