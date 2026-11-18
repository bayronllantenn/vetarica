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
    descripcion = models.TextField('Qué provee', blank=True)

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    nombre = models.CharField(max_length=100)
    codigo_proveedor = models.CharField('Código del proveedor', max_length=30, blank=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS_INSUMO)
    unidad = models.CharField(max_length=20, choices=UNIDADES_INSUMO, default='unidades')
    stock_actual = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    costo = models.PositiveIntegerField('Costo neto', default=0)
    ganancia = models.PositiveIntegerField('Ganancia (%)', default=0)
    activo = models.BooleanField(default=True)
    proveedores = models.ManyToManyField(Proveedor, blank=True, related_name='insumos')

    def __str__(self):
        return self.nombre

    def precio_venta(self):
        con_ganancia = self.costo + self.costo * self.ganancia // 100
        return con_ganancia + con_ganancia * IVA // 100

    def proximo_lote(self):
        return self.lotes.filter(cantidad__gt=0, fecha_vencimiento__isnull=False).select_related('orden').order_by('fecha_vencimiento').first()

    def stock_vencido(self):
        vencido = 0
        for lote in self.lotes.filter(cantidad__gt=0, fecha_vencimiento__lt=timezone.localdate()):
            vencido = vencido + lote.cantidad
        return vencido

    def stock_disponible(self):
        return self.stock_actual - self.stock_vencido()

    def tiene_stock_bajo(self):
        if self.stock_actual <= self.stock_minimo:
            return True
        return False

    def lotes_con_fecha(self):
        return self.lotes.filter(cantidad__gt=0, fecha_vencimiento__isnull=False).select_related('orden').order_by('fecha_vencimiento', 'id')

    def unidades_sin_fecha(self):
        total = 0
        for lote in self.lotes.filter(cantidad__gt=0, fecha_vencimiento__isnull=True):
            total = total + lote.cantidad
        return total

    def estado_vencimiento(self):
        return estado_de_fecha(self.fecha_vencimiento)


def estado_de_fecha(fecha):
    if fecha is None:
        return ''

    hoy = timezone.localdate()
    if fecha < hoy:
        return 'Vencido'
    if fecha <= hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO):
        return 'Por vencer'
    return ''


class OrdenCompra(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    numero_documento = models.CharField('N° del documento', max_length=30, blank=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordenes')
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordenes_compra')

    def __str__(self):
        return self.codigo

# generar id aleatoria para las ordenes de compra colegas
def crear_orden_compra(usuario, numero_documento='', proveedor=None):
    codigo = 'OC-' + get_random_string(6, 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    while OrdenCompra.objects.filter(codigo=codigo).exists():
        codigo = 'OC-' + get_random_string(6, 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    return OrdenCompra.objects.create(codigo=codigo, numero_documento=numero_documento, proveedor=proveedor, registrado_por=usuario)


def buscar_orden_repetida(numero_documento):
    if numero_documento == '':
        return None
    return OrdenCompra.objects.filter(numero_documento=numero_documento).first()


class Lote(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE, related_name='lotes')
    orden = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name='lotes')
    cantidad = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField(null=True, blank=True)
    fecha_ingreso = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.cantidad} {self.insumo.nombre}'

    def estado_vencimiento(self):
        return estado_de_fecha(self.fecha_vencimiento)


class Movimiento(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='movimientos')
    orden = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
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


def descontar_de_lotes(insumo, cantidad):
    hoy = timezone.localdate()
    con_fecha = list(insumo.lotes.filter(cantidad__gt=0, fecha_vencimiento__gte=hoy).order_by('fecha_vencimiento', 'id'))
    sin_fecha = list(insumo.lotes.filter(cantidad__gt=0, fecha_vencimiento__isnull=True).order_by('id'))
    falta = cantidad
    for lote in con_fecha + sin_fecha:
        if falta == 0:
            break
        if lote.cantidad <= falta:
            falta = falta - lote.cantidad
            lote.cantidad = 0
        else:
            lote.cantidad = lote.cantidad - falta
            falta = 0
        lote.save()


def actualizar_vencimiento(insumo):
    lote = insumo.proximo_lote()
    if lote is None:
        insumo.fecha_vencimiento = None
    else:
        insumo.fecha_vencimiento = lote.fecha_vencimiento
    insumo.save()


def dar_de_baja_lote(lote, usuario):
    insumo = lote.insumo
    cantidad = lote.cantidad
    insumo.stock_actual = insumo.stock_actual - cantidad
    insumo.save()
    lote.cantidad = 0
    lote.save()
    actualizar_vencimiento(insumo)
    Movimiento.objects.create(insumo=insumo, tipo='Salida', cantidad=cantidad, motivo='Baja por vencimiento', registrado_por=usuario, orden=lote.orden)


def registrar_movimiento(insumo, tipo, cantidad, motivo='', ficha=None, usuario=None, orden=None, vencimiento=None, proveedor=None):
    if tipo == 'Salida' and cantidad > insumo.stock_disponible():
        return False

    if tipo == 'Entrada':
        insumo.stock_actual = insumo.stock_actual + cantidad
        insumo.save()
        Lote.objects.create(insumo=insumo, orden=orden, cantidad=cantidad, fecha_vencimiento=vencimiento)
    else:
        insumo.stock_actual = insumo.stock_actual - cantidad
        insumo.save()
        descontar_de_lotes(insumo, cantidad)
    actualizar_vencimiento(insumo)

    Movimiento.objects.create(insumo=insumo, tipo=tipo, cantidad=cantidad, motivo=motivo, ficha=ficha, registrado_por=usuario, orden=orden, proveedor=proveedor)
    return True
