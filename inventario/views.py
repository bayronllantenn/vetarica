from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from citas.views import separar_miles
from usuarios.views import es_personal_clinica, es_veterinaria
from .forms import MovimientoForm, ProveedorForm
from .models import Insumo, Movimiento, Proveedor, registrar_movimiento
from .ocr import buscar_insumo, leer_texto, separar_productos

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


def leer_orden(foto):
    filas = []
    try:
        texto = leer_texto(foto)
    except Exception:
        return filas
    if texto is None:
        return filas

    for producto in separar_productos(texto):
        filas.append({'nombre': producto['nombre'], 'cantidad': producto['cantidad'], 'precio': producto['precio'], 'insumo': buscar_insumo(producto['nombre'])})
    return filas


def elegir_insumo(insumo_id, nombre):
    if insumo_id.isdigit():
        return Insumo.objects.filter(id=insumo_id).first()
    if insumo_id == 'nuevo' and nombre != '':
        insumo = Insumo.objects.filter(nombre__iexact=nombre).first()
        if insumo is None:
            insumo = Insumo(nombre=nombre, categoria='Otro')
        return insumo
    return None


def registrar_orden(request):
    nombres = request.POST.getlist('nombre')
    insumos = request.POST.getlist('insumo')
    cantidades = request.POST.getlist('cantidad')
    precios = request.POST.getlist('precio')

    registradas = 0
    for i in range(len(insumos)):
        insumo = elegir_insumo(insumos[i], nombres[i].strip())
        if insumo is None or not cantidades[i].isdigit() or int(cantidades[i]) == 0:
            continue

        if precios[i].isdigit():
            insumo.costo = int(precios[i])
        registrar_movimiento(insumo, 'Entrada', int(cantidades[i]), 'Orden de compra', None, request.user)
        registradas = registradas + 1

    if registradas == 0:
        messages.error(request, 'No se registró ninguna entrada. Elige el insumo de cada producto.')
        return redirect('orden_compra')
    messages.success(request, f'Se registraron {registradas} entradas desde la orden de compra.')
    return redirect('movimientos')


@never_cache
@login_required(login_url='sin_acceso')
def orden_compra(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST' and 'registrar' in request.POST:
        return registrar_orden(request)

    filas = []
    if request.method == 'POST':
        foto = request.FILES.get('foto')
        if foto is None:
            messages.error(request, 'Sube la foto de la orden de compra.')
            return redirect('orden_compra')

        filas = leer_orden(foto)
        if len(filas) == 0:
            messages.error(request, 'No se pudieron leer productos en la imagen. Intenta con una foto más clara.')
            return redirect('orden_compra')

    context = {'filas': filas, 'insumos': Insumo.objects.order_by('nombre')}
    return render(request, 'inventario/orden_compra.html', context)


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
                return redirect('movimientos')
            messages.error(request, f'No hay stock suficiente. Quedan {insumo.stock_actual} de {insumo.nombre}.')
    else:
        form = MovimientoForm()

    return render(request, 'inventario/movimiento_form.html', {'form': form})

@never_cache
@login_required(login_url='sin_acceso')
def movimientos(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    insumo_id = request.GET.get('insumo', '')
    tipo = request.GET.get('tipo', '')

    lista = Movimiento.objects.select_related('insumo', 'registrado_por').order_by('-fecha')
    if insumo_id.isdigit():
        insumo_id = int(insumo_id)
        lista = lista.filter(insumo_id=insumo_id)
    if tipo == 'Entrada' or tipo == 'Salida':
        lista = lista.filter(tipo=tipo)
    context = {'movimientos': lista,'insumos': Insumo.objects.order_by('nombre'),'insumo_id': insumo_id,'tipo': tipo,}
    return render(request, 'inventario/movimientos.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def inventario(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        insumo = get_object_or_404(Insumo, id=request.POST.get('insumo_id', '0'))
        ganancia = request.POST.get('ganancia', '').strip()
        if ganancia.isdigit():
            insumo.ganancia = int(ganancia)
            insumo.save()
            messages.success(request, f'Beneficio de {insumo.nombre} actualizado a {insumo.ganancia}%.')
        else:
            messages.error(request, 'El beneficio debe ser un número entero, por ejemplo 30.')

        pagina = request.POST.get('page', '1')
        if not pagina.isdigit():
            pagina = '1'
        datos = urlencode({'page': pagina, 'buscar': request.POST.get('buscar', '')})
        return redirect(reverse('inventario') + '?' + datos + '#cerrar')

    buscar = request.GET.get('buscar', '').strip()
    insumos = Insumo.objects.order_by('categoria', 'nombre')
    if buscar:
        insumos = insumos.filter(nombre__icontains=buscar)

    paginador = Paginator(insumos, 8)
    page_obj = paginador.get_page(request.GET.get('page'))

    lista = []
    for insumo in page_obj:
        neto = None
        beneficio = None
        total = None
        if insumo.costo > 0:
            ganancia = insumo.costo * insumo.ganancia // 100
            neto = separar_miles(insumo.costo)
            beneficio = separar_miles(ganancia)
            total = separar_miles(insumo.costo + ganancia)
        lista.append({'insumo': insumo, 'neto': neto, 'beneficio': beneficio, 'total': total})

    return render(request, 'inventario/inventario.html', {'lista': lista, 'page_obj': page_obj, 'buscar': buscar})