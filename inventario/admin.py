from django.contrib import admin
from .models import Insumo, Movimiento, Proveedor, Venta


class InsumoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'stock_actual', 'costo', 'ganancia', 'precio_venta')


admin.site.register(Proveedor)
admin.site.register(Insumo, InsumoAdmin)
admin.site.register(Movimiento)
admin.site.register(Venta)
