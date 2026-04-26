from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("eventos", "0003_inscripcion_asistencia_y_datos_extra"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'eventos_evento'
                      AND column_name = 'recordatorio_24h_enviado'
                ) THEN
                    ALTER TABLE eventos_evento
                    ALTER COLUMN recordatorio_24h_enviado SET DEFAULT false;
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'eventos_evento'
                      AND column_name = 'recordatorio_1h_enviado'
                ) THEN
                    ALTER TABLE eventos_evento
                    ALTER COLUMN recordatorio_1h_enviado SET DEFAULT false;
                END IF;
            END
            $$;
            """,
            reverse_sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'eventos_evento'
                      AND column_name = 'recordatorio_24h_enviado'
                ) THEN
                    ALTER TABLE eventos_evento
                    ALTER COLUMN recordatorio_24h_enviado DROP DEFAULT;
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'eventos_evento'
                      AND column_name = 'recordatorio_1h_enviado'
                ) THEN
                    ALTER TABLE eventos_evento
                    ALTER COLUMN recordatorio_1h_enviado DROP DEFAULT;
                END IF;
            END
            $$;
            """,
        ),
    ]
