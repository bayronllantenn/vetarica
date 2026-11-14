from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string

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

IVA = 19


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    rut = models.CharField('RUT', max_length=12, unique=True, error_messages={'unique': 'Ya existe un proveedor con ese RUT.'})
    contacto = models.CharField(max_length=100, blank=True)
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
    costo = models.PositiveIntegerField('Costo neto', default=0)
    ganancia = models.PositiveIntegerField('Ganancia (%)', default=0)

    def __str__(self):
        return self.nombre

    def precio_venta(self):
        con_ganancia = self.costo + self.costo * self.ganancia // 100
        return con_ganancia + con_ganancia * IVA // 100

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


class OrdenCompra(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordenes_compra')

    def __str__(self):
        return self.codigo

# generar id aleatoria para las ordenes de compra colegas
def crear_orden_compra(usuario):
    codigo = 'OC-' + get_random_string(6, 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    while OrdenCompra.objects.filter(codigo=codigo).exists():
        codigo = 'OC-' + get_random_string(6, 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    return OrdenCompra.objects.create(codigo=codigo, registrado_por=usuario)


class Movimiento(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='movimientos')
    orden = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TIPOS_MOVIMIENTO)
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    ficha = models.ForeignKey('citas.FichaMedica',on_delete=models.SET_NULL,null=True,blank=True,related_name='movimientos_inventario',)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,)

    def __str__(self):
        return f'{self.tipo} de {self.cantidad} {self.insumo.nombre}'


class Venta(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='ventas')
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.PositiveIntegerField()
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='compras_insumos')
    nombre_cliente = models.CharField(max_length=100, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_registradas')

    def __str__(self):
        return f'Venta de {self.cantidad} {self.insumo.nombre}'

    def total(self):
        return self.cantidad * self.precio_unitario


def registrar_movimiento(insumo, tipo, cantidad, motivo='', ficha=None, usuario=None, orden=None):
    if tipo == 'Salida' and cantidad > insumo.stock_actual:
        return False

    if tipo == 'Entrada':
        insumo.stock_actual = insumo.stock_actual + cantidad
    else:
        insumo.stock_actual = insumo.stock_actual - cantidad
    insumo.save()

    Movimiento.objects.create(insumo=insumo, tipo=tipo, cantidad=cantidad, motivo=motivo, ficha=ficha, registrado_por=usuario, orden=orden)
    return True
