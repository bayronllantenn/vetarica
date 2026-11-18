from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0011_insumo_activo_proveedores'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimiento',
            name='proveedor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos', to='inventario.proveedor'),
        ),
    ]
