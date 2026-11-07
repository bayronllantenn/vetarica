from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from usuarios.views import es_personal_clinica
from .forms import ProveedorForm
from .models import Proveedor

@never_cache
@login_required(login_url='sin_acceso')
def proveedores(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    lista = Proveedor.objects.prefetch_related('insumos').order_by('nombre')
    return render(request, 'inventario/proveedores.html', {'proveedores': lista})

@login_required(login_url='sin_acceso')
def crear_proveedor(request):
    if not es_personal_clinica(request.user):
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
    if not es_personal_clinica(request.user):
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
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    if request.method == 'POST':
        proveedor.delete()
        messages.success(request, f'{proveedor.nombre} fue eliminado correctamente.')
    return redirect('proveedores')
