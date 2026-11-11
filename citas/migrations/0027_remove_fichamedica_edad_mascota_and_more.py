from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0026_solicitudcita_recordatorio_enviado'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fichamedica',
            name='edad_mascota',
        ),
        migrations.RemoveField(
            model_name='mascota',
            name='edad_unidad',
        ),
        migrations.RemoveField(
            model_name='mascota',
            name='edad_valor',
        ),
        migrations.RemoveField(
            model_name='solicitudcita',
            name='edad_unidad_mascota',
        ),
        migrations.RemoveField(
            model_name='solicitudcita',
            name='edad_valor_mascota',
        ),
        migrations.AddField(
            model_name='fichamedica',
            name='fecha_nacimiento_mascota',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mascota',
            name='fecha_nacimiento',
            field=models.DateField(null=True),
        ),
        migrations.AddField(
            model_name='solicitudcita',
            name='fecha_nacimiento_mascota',
            field=models.DateField(blank=True, null=True),
        ),
    ]
