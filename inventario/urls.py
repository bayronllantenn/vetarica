from django.urls import path

from . import views

urlpatterns = [
    path('proveedores/', views.proveedores, name='proveedores'),
    path('proveedores/crear/', views.crear_proveedor, name='crear_proveedor'),
    path('proveedores/<int:proveedor_id>/editar/', views.editar_proveedor, name='editar_proveedor'),
    path('proveedores/<int:proveedor_id>/eliminar/', views.eliminar_proveedor, name='eliminar_proveedor'),
    path('movimientos/', views.movimientos, name='movimientos'),
    path('movimientos/nuevo/', views.nuevo_movimiento, name='nuevo_movimiento'),
]
