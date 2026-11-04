from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0025_tipoconsulta_activo'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudcita',
            name='recordatorio_enviado',
            field=models.BooleanField(default=False),
        ),
    ]