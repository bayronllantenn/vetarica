from django.urls import path

from . import views

urlpatterns = [
    path('', views.inventario, name='inventario'),
    path('proveedores/', views.proveedores, name='proveedores'),
    path('proveedores/crear/', views.crear_proveedor, name='crear_proveedor'),
    path('proveedores/<int:proveedor_id>/editar/', views.editar_proveedor, name='editar_proveedor'),
    path('proveedores/<int:proveedor_id>/eliminar/', views.eliminar_proveedor, name='eliminar_proveedor'),
    path('insumos/nuevo/', views.nuevo_insumo, name='nuevo_insumo'),
    path('insumos/<int:insumo_id>/eliminar/', views.eliminar_insumo, name='eliminar_insumo'),
    path('insumos/<int:insumo_id>/lotes/', views.lotes_insumo, name='lotes_insumo'),
    path('orden-compra/', views.orden_compra, name='orden_compra'),
    path('lotes/<int:lote_id>/dar-de-baja/', views.dar_de_baja, name='dar_de_baja'),
    path('movimientos/', views.movimientos, name='movimientos'),
    path('movimientos/nuevo/', views.nuevo_movimiento, name='nuevo_movimiento'),
    path('movimientos/orden/<str:codigo>/', views.detalle_orden, name='detalle_orden'),
]
