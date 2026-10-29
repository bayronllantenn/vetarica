from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

CATEGORIAS_INSUMO = [
    ('Medicamento', 'Medicamento'),
    ('Vacuna', 'Vacuna'),
    ('Material', 'Material'),
    ('Otro', 'Otro'),
]

UNIDADES_INSUMO = [
    ('unidades', 'Unidades'),
    ('cajas', 'Cajas'),
    ('ml', 'ml'),
]

TIPOS_MOVIMIENTO = [
    ('Entrada', 'Entrada'),
    ('Salida', 'Salida'),
]

DIAS_AVISO_VENCIMIENTO = 30


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    nombre = models.CharField(max_length=100)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS_INSUMO)
    unidad = models.CharField(max_length=20, choices=UNIDADES_INSUMO, default='unidades')
    stock_actual = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    proveedores = models.ManyToManyField(Proveedor, blank=True, related_name='insumos')

    def __str__(self):
        return self.nombre

    def tiene_stock_bajo(self):
        if self.stock_actual <= self.stock_minimo:
            return True
        return False

    def estado_vencimiento(self):
        if self.fecha_vencimiento is None:
            return ''

        hoy = timezone.localdate()
        if self.fecha_vencimiento < hoy:
            return 'Vencido'
        if self.fecha_vencimiento <= hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO):
            return 'Por vencer'
        return ''


class Movimiento(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TIPOS_MOVIMIENTO)
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    ficha = models.ForeignKey('citas.FichaMedica',on_delete=models.SET_NULL,null=True,blank=True,related_name='movimientos_inventario',)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,)

    def __str__(self):
        return f'{self.tipo} de {self.cantidad} {self.insumo.nombre}'


def registrar_movimiento(insumo, tipo, cantidad, motivo='', ficha=None, usuario=None):
    if tipo == 'Salida' and cantidad > insumo.stock_actual:
        return False

    if tipo == 'Entrada':
        insumo.stock_actual = insumo.stock_actual + cantidad
    else:
        insumo.stock_actual = insumo.stock_actual - cantidad
    insumo.save()

    Movimiento.objects.create(insumo=insumo, tipo=tipo, cantidad=cantidad, motivo=motivo, ficha=ficha, registrado_por=usuario)    
    return True
