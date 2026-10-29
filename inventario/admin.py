from django.contrib import admin
from .models import Insumo, Movimiento, Proveedor

admin.site.register(Proveedor)
admin.site.register(Insumo)
admin.site.register(Movimiento)
