from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from usuarios.views import es_personal_clinica, es_veterinaria
from .forms import MovimientoForm, ProveedorForm
from .models import Proveedor, registrar_movimiento

@never_cache
@login_required(login_url='sin_acceso')
def proveedores(request):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    buscar = request.GET.get('buscar', '').strip()
    lista = Proveedor.objects.prefetch_related('insumos').order_by('nombre')
    if buscar:
        por_nombre = lista.filter(nombre__icontains=buscar)
        por_rut = lista.filter(rut__icontains=buscar)
        por_contacto = lista.filter(contacto__icontains=buscar)
        lista = por_nombre | por_rut | por_contacto
    return render(request, 'inventario/proveedores.html', {'proveedores': lista, 'buscar': buscar})

@login_required(login_url='sin_acceso')
def crear_proveedor(request):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, f'{proveedor.nombre} fue agregado correctamente.')
            return redirect('proveedores')
    else:
        form = ProveedorForm()
    return render(request, 'inventario/proveedor_form.html', {'form': form})


@login_required(login_url='sin_acceso')
def editar_proveedor(request, proveedor_id):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            messages.success(request, f'{proveedor.nombre} fue actualizado correctamente.')
            return redirect('proveedores')
    else:
        form = ProveedorForm(instance=proveedor, initial={'insumos': proveedor.insumos.all()})
    return render(request, 'inventario/proveedor_form.html', {'form': form, 'proveedor': proveedor})

@login_required(login_url='sin_acceso')
def eliminar_proveedor(request, proveedor_id):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == 'POST':
        proveedor.delete()
        messages.success(request, f'{proveedor.nombre} fue eliminado correctamente.')
    return redirect('proveedores')


@login_required(login_url='sin_acceso')
def nuevo_movimiento(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = MovimientoForm(request.POST)
        if form.is_valid():
            insumo = form.cleaned_data['insumo']
            tipo = form.cleaned_data['tipo']
            cantidad = form.cleaned_data['cantidad']
            motivo = form.cleaned_data['motivo']

            se_registro = registrar_movimiento(insumo, tipo, cantidad, motivo, None, request.user)
            if se_registro:
                messages.success(request, f'{tipo} de {cantidad} {insumo.nombre} registrada.')
                return redirect('nuevo_movimiento')
            messages.error(request, f'No hay stock suficiente. Quedan {insumo.stock_actual} de {insumo.nombre}.')
    else:
        form = MovimientoForm()

    return render(request, 'inventario/movimiento_form.html', {'form': form})
