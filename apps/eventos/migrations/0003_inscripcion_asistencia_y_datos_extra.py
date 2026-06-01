from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("eventos", "0002_evento_inscripcion_config"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE eventos_inscripcion
                    ADD COLUMN IF NOT EXISTS asistencia_marcada_en timestamp with time zone NULL;
                    """,
                    reverse_sql="""
                    ALTER TABLE eventos_inscripcion
                    DROP COLUMN IF EXISTS asistencia_marcada_en;
                    """,
                ),
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE eventos_inscripcion
                    ADD COLUMN IF NOT EXISTS asistio boolean NOT NULL DEFAULT false;
                    """,
                    reverse_sql="""
                    ALTER TABLE eventos_inscripcion
                    DROP COLUMN IF EXISTS asistio;
                    """,
                ),
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE eventos_inscripcion
                    ADD COLUMN IF NOT EXISTS datos_extra jsonb NOT NULL DEFAULT '{}'::jsonb;
                    """,
                    reverse_sql="""
                    ALTER TABLE eventos_inscripcion
                    DROP COLUMN IF EXISTS datos_extra;
                    """,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="inscripcion",
                    name="asistencia_marcada_en",
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="inscripcion",
                    name="asistio",
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name="inscripcion",
                    name="datos_extra",
                    field=models.JSONField(blank=True, default=dict),
                ),
            ],
        ),
    ]
