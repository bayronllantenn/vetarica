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
from .forms import BajaForm, InsumoForm, ProveedorForm, VentaForm
from .models import CATEGORIAS_INSUMO, Insumo, Lote, Movimiento, OrdenCompra, Proveedor, Venta, buscar_orden_repetida, crear_orden_compra, dar_de_baja_lote, registrar_movimiento
from .ocr import buscar_insumo, buscar_proveedor, leer_numero_documento, leer_proveedor, leer_texto, separar_productos

def alertas(request):
    if not request.user.is_authenticated or not es_personal_clinica(request.user):
        return {}

    lista = []
    for insumo in Insumo.objects.order_by('nombre'):
        if insumo.tiene_stock_bajo():
            lista.append({'tipo': 'Bajo stock', 'insumo': insumo})

    lotes = Lote.objects.filter(cantidad__gt=0, alerta_oculta=False, fecha_vencimiento__isnull=False)
    for lote in lotes.select_related('insumo', 'orden').order_by('fecha_vencimiento'):
        estado = lote.estado_vencimiento()
        if estado != '':
            lista.append({'tipo': estado, 'insumo': lote.insumo, 'lote': lote})

    paginador = Paginator(lista, 3)
    pagina = paginador.get_page(request.GET.get('alertas'))

    datos = request.GET.copy()
    if 'alertas' in datos:
        del datos['alertas']
    url = '?'
    if datos:
        url = '?' + datos.urlencode() + '&'

    return {'alertas': pagina, 'alertas_url': url}

@login_required(login_url='sin_acceso')
def ocultar_alerta(request, lote_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    lote = get_object_or_404(Lote, id=lote_id)
    if request.method == 'POST':
        lote.alerta_oculta = True
        lote.save()

    volver = request.POST.get('volver', '')
    if not volver.startswith('/') or volver.startswith('//'):
        volver = reverse('inventario')
    return redirect(volver + '#notificaciones')

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
    paginador = Paginator(lista, 10)
    page_obj = paginador.get_page(request.GET.get('page'))
    return render(request, 'inventario/proveedores.html', {'proveedores': page_obj, 'page_obj': page_obj, 'buscar': buscar, 'sugerencias': Proveedor.objects.order_by('nombre')})

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
        return Insumo.objects.filter(id=insumo_id, activo=True).first()
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
            insumo.activo = True
            registrar_movimiento(insumo, 'Entrada', unidades, 'Orden de compra', None, request.user, orden, vencimiento)
            if proveedor is not None:
                insumo.proveedores.add(proveedor)
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

    context = {'filas': filas, 'numero': numero, 'insumos': Insumo.objects.filter(activo=True).order_by('nombre'), 'proveedores': Proveedor.objects.order_by('nombre'), 'proveedor': proveedor, 'elegido': elegido}
    return render(request, 'inventario/orden_compra.html', context)


@login_required(login_url='sin_acceso')
def nuevo_movimiento(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = BajaForm(request.POST)
        if form.is_valid():
            insumo = form.cleaned_data['insumo']
            cantidad = form.cleaned_data['cantidad']
            motivo = form.cleaned_data['motivo']

            se_registro = registrar_movimiento(insumo, 'Salida', cantidad, motivo=motivo, usuario=request.user)
            if se_registro:
                messages.success(request, f'Baja de {cantidad} {insumo.nombre} registrada.')
                return redirect('movimientos')
            messages.error(request, f'No hay stock suficiente. Quedan {insumo.stock_disponible()} de {insumo.nombre} sin vencer.')
    else:
        form = BajaForm()

    context = {
        'form': form,
        'titulo': 'Registrar baja',
        'subtitulo': 'Descuenta del stock los insumos que se rompieron, se perdieron o se usaron fuera de una atención.',
        'volver': 'movimientos',
    }
    return render(request, 'inventario/movimiento_form.html', context)


def nombre_con_precio(insumo):
    return f'{insumo.nombre} - ${separar_miles(insumo.precio_venta())} (quedan {insumo.stock_actual})'


@login_required(login_url='sin_acceso')
def registrar_venta(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = VentaForm(request.POST)
        if form.is_valid():
            insumo = form.cleaned_data['insumo']
            cantidad = form.cleaned_data['cantidad']
            cliente = form.cleaned_data['cliente'].strip()
            precio = insumo.precio_venta()

            if precio == 0:
                messages.error(request, f'{insumo.nombre} no tiene costo registrado. Edítalo en el inventario antes de venderlo.')
            else:
                with transaction.atomic():
                    se_registro = registrar_movimiento(insumo, 'Salida', cantidad, motivo=f'Venta a {cliente}', usuario=request.user)
                    if se_registro:
                        Venta.objects.create(insumo=insumo, cantidad=cantidad, precio_unitario=precio, nombre_cliente=cliente, registrado_por=request.user)
                if se_registro:
                    messages.success(request, f'Venta de {cantidad} {insumo.nombre} registrada: ${separar_miles(precio * cantidad)}.')
                    return redirect('inventario')
                messages.error(request, f'No hay stock suficiente. Quedan {insumo.stock_disponible()} de {insumo.nombre} sin vencer.')
    else:
        form = VentaForm()

    form.fields['insumo'].label_from_instance = nombre_con_precio
    context = {
        'form': form,
        'titulo': 'Registrar venta',
        'subtitulo': 'El precio se calcula solo con el costo, el % de ganancia y el IVA, y el stock se descuenta.',
        'volver': 'inventario',
    }
    return render(request, 'inventario/movimiento_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def movimientos(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    insumo_id = request.GET.get('insumo', '')
    tipo = request.GET.get('tipo', '')

    lista = Movimiento.objects.select_related('insumo', 'registrado_por', 'orden', 'proveedor').order_by('-fecha')
    if insumo_id.isdigit():
        insumo_id = int(insumo_id)
        lista = lista.filter(insumo_id=insumo_id)
    if tipo == 'Entrada' or tipo == 'Salida':
        lista = lista.filter(tipo=tipo)

    filas = []
    ordenes_vistas = []
    for movimiento in lista:
        if movimiento.orden is None or movimiento.tipo != 'Entrada' or insumo_id != '':
            filas.append({'movimiento': movimiento, 'orden': None})
        elif movimiento.orden_id not in ordenes_vistas:
            ordenes_vistas.append(movimiento.orden_id)
            productos = movimiento.orden.movimientos.filter(tipo='Entrada').count()
            filas.append({'movimiento': movimiento, 'orden': movimiento.orden, 'productos': productos})

    paginador = Paginator(filas, 10)
    page_obj = paginador.get_page(request.GET.get('page'))
    context = {'filas': page_obj, 'page_obj': page_obj, 'insumos': Insumo.objects.order_by('nombre'), 'insumo_id': insumo_id, 'tipo': tipo}
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
    if request.POST.get('volver', '') == 'lotes':
        return redirect('lotes_insumo', insumo_id=lote.insumo_id)
    return redirect('inventario')


@never_cache
@login_required(login_url='sin_acceso')
def lotes_insumo(request, insumo_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    insumo = get_object_or_404(Insumo, id=insumo_id)
    context = {'insumo': insumo, 'lotes': insumo.lotes_con_fecha(), 'sin_fecha': insumo.unidades_sin_fecha()}
    return render(request, 'inventario/lotes_insumo.html', context)


@never_cache
@login_required(login_url='sin_acceso')
def detalle_orden(request, codigo):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    orden = get_object_or_404(OrdenCompra, codigo=codigo)
    lista = orden.movimientos.filter(tipo='Entrada').select_related('insumo').order_by('insumo__nombre')
    return render(request, 'inventario/detalle_orden.html', {'orden': orden, 'movimientos': lista})


@login_required(login_url='sin_acceso')
def nuevo_insumo(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = InsumoForm(request.POST)
        if form.is_valid():
            stock_inicial = form.cleaned_data['stock_inicial']
            vencimiento = form.cleaned_data['vencimiento']
            with transaction.atomic():
                insumo = form.save()
                if stock_inicial > 0:
                    registrar_movimiento(insumo, 'Entrada', stock_inicial, 'Stock inicial', None, request.user, None, vencimiento)
            messages.success(request, f'{insumo.nombre} fue agregado al inventario.')
            return redirect('inventario')
    else:
        form = InsumoForm()

    return render(request, 'inventario/insumo_form.html', {'form': form})


@login_required(login_url='sin_acceso')
def eliminar_insumo(request, insumo_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    insumo = get_object_or_404(Insumo, id=insumo_id, activo=True)
    if request.method == 'POST':
        if insumo.movimientos.exists() or insumo.ventas.exists():
            insumo.activo = False
            insumo.save()
            messages.success(request, f'{insumo.nombre} fue eliminado. Su historial se conserva.')
        else:
            insumo.delete()
            messages.success(request, f'{insumo.nombre} fue eliminado.')
    return redirect('inventario')

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
        insumo = get_object_or_404(Insumo, id=request.POST.get('insumo_id', '0'), activo=True)
        ganancia = request.POST.get('ganancia', '').strip()
        categoria = request.POST.get('categoria', '')
        stock_minimo = request.POST.get('stock_minimo', '').strip()
        if not ganancia.isdigit():
            messages.error(request, 'El beneficio debe ser un número entero, por ejemplo 30.')
        elif not stock_minimo.isdigit():
            messages.error(request, 'El stock mínimo debe ser un número entero, por ejemplo 5.')
        elif not es_categoria_valida(categoria):
            messages.error(request, 'Elige una categoría de la lista.')
        else:
            insumo.ganancia = int(ganancia)
            insumo.categoria = categoria
            insumo.stock_minimo = int(stock_minimo)
            insumo.save()
            messages.success(request, f'{insumo.nombre} fue actualizado.')

        pagina = request.POST.get('page', '1')
        if not pagina.isdigit():
            pagina = '1'
        datos = urlencode({'page': pagina, 'buscar': request.POST.get('buscar', ''), 'eliminados': request.POST.get('eliminados', '')})
        return redirect(reverse('inventario') + '?' + datos + '#cerrar')

    buscar = request.GET.get('buscar', '').strip()
    eliminados = request.GET.get('eliminados', '')
    if eliminados == '1':
        ver_eliminados = True
    else:
        ver_eliminados = False

    if ver_eliminados:
        insumos = Insumo.objects.filter(activo=False).order_by('categoria', 'nombre')
    else:
        insumos = Insumo.objects.filter(activo=True).order_by('categoria', 'nombre')
    if buscar:
        insumos = insumos.filter(nombre__icontains=buscar)

    paginador = Paginator(insumos, 10)
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

        primer_lote = insumo.lotes_con_fecha().first()
        cantidad_lotes = insumo.lotes_con_fecha().count()
        sin_fecha = insumo.unidades_sin_fecha()
        if sin_fecha > 0:
            cantidad_lotes = cantidad_lotes + 1

        lista.append({'insumo': insumo, 'neto': neto, 'beneficio': beneficio, 'total': total, 'primer_lote': primer_lote, 'sin_fecha': sin_fecha, 'cantidad_lotes': cantidad_lotes})

    return render(request, 'inventario/inventario.html', {'lista': lista, 'page_obj': page_obj, 'buscar': buscar, 'ver_eliminados': ver_eliminados, 'categorias': CATEGORIAS_INSUMO, 'sugerencias': Insumo.objects.order_by('nombre')})
