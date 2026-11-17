from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from citas.views import separar_miles
from usuarios.forms import validar_rut
from usuarios.views import es_personal_clinica, es_veterinaria
from .forms import MovimientoForm, ProveedorForm
from .models import CATEGORIAS_INSUMO, Insumo, Lote, Movimiento, OrdenCompra, Proveedor, buscar_orden_repetida, crear_orden_compra, dar_de_baja_lote, registrar_movimiento
from .ocr import buscar_insumo, buscar_proveedor, leer_numero_documento, leer_proveedor, leer_texto, separar_productos

@never_cache
@login_required(login_url='sin_acceso')
def proveedores(request):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    buscar = request.GET.get('buscar', '').strip()
    lista = Proveedor.objects.order_by('nombre')
    if buscar:
        por_nombre = lista.filter(nombre__icontains=buscar)
        por_rut = lista.filter(rut__icontains=buscar)
        por_contacto = lista.filter(contacto__icontains=buscar)
        por_descripcion = lista.filter(descripcion__icontains=buscar)
        lista = por_nombre | por_rut | por_contacto | por_descripcion
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
        form = ProveedorForm(instance=proveedor)
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
    resultado = {'filas': [], 'numero': '', 'proveedor': {'nombre': '', 'rut': '', 'contacto': '', 'telefono': ''}}
    try:
        lectura = leer_texto(foto)
    except Exception:
        return resultado
    if lectura is None:
        return resultado

    texto = lectura['ParsedText']
    resultado['numero'] = leer_numero_documento(texto)
    resultado['proveedor'] = leer_proveedor(lectura['TextOverlay']['Lines'])
    for producto in separar_productos(texto):
        resultado['filas'].append({'nombre': producto['nombre'], 'cantidad': producto['cantidad'], 'precio': producto['precio'], 'por_caja': producto['por_caja'], 'codigo': producto['codigo'], 'insumo': buscar_insumo(producto['nombre'], producto['codigo'])})
    return resultado

def elegir_proveedor(request):
    eleccion = request.POST.get('proveedor', '')
    if eleccion.isdigit():
        return Proveedor.objects.filter(id=eleccion).first()
    if eleccion != 'nuevo':
        return None

    nombre = request.POST.get('proveedor_nombre', '').strip()
    try:
        rut = validar_rut(request.POST.get('proveedor_rut', ''))
    except ValidationError:
        return None
    if nombre == '':
        return None

    proveedor = Proveedor.objects.filter(rut=rut).first()
    if proveedor is None:
        contacto = request.POST.get('proveedor_contacto', '').strip()
        telefono = request.POST.get('proveedor_telefono', '').strip()
        proveedor = Proveedor.objects.create(nombre=nombre, rut=rut, contacto=contacto, telefono=telefono)
    return proveedor


def aviso_orden_repetida(request, numero):
    repetida = buscar_orden_repetida(numero)
    if repetida is None:
        return False
    fecha = repetida.fecha.strftime('%d/%m/%Y')
    messages.error(request, f'El documento N° {numero} ya fue registrado el {fecha} como {repetida.codigo}.')
    return True


def elegir_insumo(insumo_id, nombre, codigo):
    if insumo_id.isdigit():
        return Insumo.objects.filter(id=insumo_id).first()
    if insumo_id == 'nuevo' and nombre != '':
        insumo = None
        if codigo != '':
            insumo = Insumo.objects.filter(codigo_proveedor__iexact=codigo).first()
        if insumo is None:
            insumo = Insumo.objects.filter(nombre__iexact=nombre).first()
        if insumo is None:
            insumo = Insumo(nombre=nombre, categoria='Otro')
        return insumo
    return None


def leer_fecha(texto):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def registrar_orden(request):
    nombres = request.POST.getlist('nombre')
    insumos = request.POST.getlist('insumo')
    cantidades = request.POST.getlist('cantidad')
    precios = request.POST.getlist('precio')
    vencimientos = request.POST.getlist('vencimiento')
    por_cajas = request.POST.getlist('por_caja')
    codigos = request.POST.getlist('codigo')
    numero =request.POST.get('numero_documento', '').strip()

    if aviso_orden_repetida(request, numero):
        return redirect('orden_compra')

    with transaction.atomic():
        proveedor = elegir_proveedor(request)
        if request.POST.get('proveedor') == 'nuevo' and proveedor is None:
            messages.error(request, 'El nombre o el RUT del proveedor no es válido.')
            return redirect('orden_compra')

        orden = crear_orden_compra(request.user, numero, proveedor)
        registradas = 0
        for i in range(len(insumos)):
            codigo = codigos[i].strip()
            insumo = elegir_insumo(insumos[i], nombres[i].strip(), codigo)
            if insumo is None or not cantidades[i].isdigit() or int(cantidades[i]) == 0:
                continue
            if codigo != '' and insumo.codigo_proveedor == '':
                insumo.codigo_proveedor = codigo

            por_caja = 1
            if por_cajas[i].isdigit() and int(por_cajas[i]) > 0:
                por_caja = int(por_cajas[i])

            if precios[i].isdigit():
                insumo.costo = int(precios[i]) // por_caja
            vencimiento = leer_fecha(vencimientos[i])
            unidades = int(cantidades[i]) * por_caja
            registrar_movimiento(insumo, 'Entrada', unidades, 'Orden de compra', None, request.user, orden, vencimiento)
            registradas = registradas + 1

        if registradas == 0:
            transaction.set_rollback(True)

    if registradas == 0:
        messages.error(request, 'No se registró ninguna entrada. Elige el insumo de cada producto.')
        return redirect('orden_compra')
    messages.success(request, f'Orden {orden.codigo} registrada con {registradas} productos.')
    return redirect('movimientos')


@never_cache
@login_required(login_url='sin_acceso')
def orden_compra(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST' and 'registrar' in request.POST:
        return registrar_orden(request)

    if request.method != 'POST':
        return render(request, 'inventario/orden_compra.html', {'filas': []})

    foto = request.FILES.get('foto')
    if foto is None:
        messages.error(request, 'Sube la foto de la orden de compra.')
        return redirect('orden_compra')

    resultado = leer_orden(foto)
    filas = resultado['filas']
    numero = resultado['numero']
    if len(filas) == 0:
        messages.error(request, 'No se pudieron leer productos en la imagen. Intenta con una foto más clara.')
        return redirect('orden_compra')
    if aviso_orden_repetida(request, numero):
        return redirect('orden_compra')

    proveedor = resultado['proveedor']
    elegido = 'nuevo'
    if proveedor['nombre'] == '' and proveedor['rut'] == '':
        elegido = ''
    encontrado = buscar_proveedor(proveedor)
    if encontrado is not None:
        elegido = encontrado.id
        proveedor = {'nombre': encontrado.nombre, 'rut': encontrado.rut, 'contacto': encontrado.contacto, 'telefono': encontrado.telefono}

    context = {'filas': filas, 'numero': numero, 'insumos': Insumo.objects.order_by('nombre'), 'proveedores': Proveedor.objects.order_by('nombre'), 'proveedor': proveedor, 'elegido': elegido}
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
            messages.error(request, f'No hay stock suficiente. Quedan {insumo.stock_disponible()} de {insumo.nombre} sin vencer.')
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

    lista = Movimiento.objects.select_related('insumo', 'registrado_por', 'orden').order_by('-fecha')
    if insumo_id.isdigit():
        insumo_id = int(insumo_id)
        lista = lista.filter(insumo_id=insumo_id)
    if tipo == 'Entrada' or tipo == 'Salida':
        lista = lista.filter(tipo=tipo)

    filas = []
    ordenes_vistas = []
    for movimiento in lista:
        if movimiento.orden is None or insumo_id != '':
            filas.append({'movimiento': movimiento, 'orden': None})
        elif movimiento.orden_id not in ordenes_vistas:
            ordenes_vistas.append(movimiento.orden_id)
            filas.append({'movimiento': movimiento, 'orden': movimiento.orden})

    context = {'filas': filas, 'insumos': Insumo.objects.order_by('nombre'), 'insumo_id': insumo_id, 'tipo': tipo}
    return render(request, 'inventario/movimientos.html', context)


@login_required(login_url='sin_acceso')
def dar_de_baja(request, lote_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    lote = get_object_or_404(Lote.objects.select_related('insumo'), id=lote_id)
    if request.method == 'POST' and lote.cantidad > 0 and lote.estado_vencimiento() == 'Vencido':
        cantidad = lote.cantidad
        dar_de_baja_lote(lote, request.user)
        messages.success(request, f'Se dieron de baja {cantidad} {lote.insumo.nombre} vencidos.')
    return redirect('inventario')


@never_cache
@login_required(login_url='sin_acceso')
def detalle_orden(request, codigo):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    orden = get_object_or_404(OrdenCompra, codigo=codigo)
    lista = orden.movimientos.select_related('insumo').order_by('insumo__nombre')
    return render(request, 'inventario/detalle_orden.html', {'orden': orden, 'movimientos': lista})

def es_categoria_valida(categoria):
    for valor, texto in CATEGORIAS_INSUMO:
        if valor == categoria:
            return True
    return False


@never_cache
@login_required(login_url='sin_acceso')
def inventario(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        insumo = get_object_or_404(Insumo, id=request.POST.get('insumo_id', '0'))
        ganancia = request.POST.get('ganancia', '').strip()
        categoria = request.POST.get('categoria', '')
        if not ganancia.isdigit():
            messages.error(request, 'El beneficio debe ser un número entero, por ejemplo 30.')
        elif not es_categoria_valida(categoria):
            messages.error(request, 'Elige una categoría de la lista.')
        else:
            insumo.ganancia = int(ganancia)
            insumo.categoria = categoria
            insumo.save()
            messages.success(request, f'{insumo.nombre} actualizado: {insumo.categoria}, {insumo.ganancia}% de beneficio.')

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

    return render(request, 'inventario/inventario.html', {'lista': lista, 'page_obj': page_obj, 'buscar': buscar, 'categorias': CATEGORIAS_INSUMO})