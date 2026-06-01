from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("eventos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="campo_correo_label",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="evento",
            name="campo_nombre_label",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="evento",
            name="enviar_confirmacion_email",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="evento",
            name="form_externo_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="evento",
            name="sheet_respuestas_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="evento",
            name="tipo_inscripcion",
            field=models.CharField(
                choices=[
                    ("interno", "Formulario interno UNIBot"),
                    ("google_form", "Google Form externo"),
                ],
                default="interno",
                max_length=20,
            ),
        ),
    ]
