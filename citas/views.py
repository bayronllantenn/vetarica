from datetime import date, datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from usuarios.models import Persona
from usuarios.views import es_personal_clinica
from .forms import FichaMedicaForm, MascotaForm, ReagendarCitaForm, SolicitudCitaForm, obtener_horas_disponibles, rango_del_dia
from .models import BloqueoHorario, FichaMedica, Mascota, SolicitudCita
from .utils import get_webpay_transaction

def puede_ver_solicitud(request, solicitud):
    if solicitud.cliente_id:
        return request.user.is_authenticated and request.user.id == solicitud.cliente_id

    return solicitud.id in request.session.get('mis_solicitudes', [])


def enviar_correo_confirmacion(solicitud):
    if not solicitud.email:
        return

    fecha = timezone.localtime(solicitud.fecha_hora).strftime('%d/%m/%Y %H:%M')
    asunto = 'Recordatorio de tu cita - Vet Arica'
    mensaje = (
        f'Hola {solicitud.nombre}, te recordamos tu cita para {solicitud.nombre_mascota} '
        f'el {fecha}. Te esperamos en Vet Arica.'
    )
    try:
        send_mail(asunto, mensaje, None, [solicitud.email])
    except Exception:
        pass


@login_required(login_url='sin_acceso')
def agregar_mascota(request):
    es_personal = es_personal_clinica(request.user)

    clientes = []
    dueno = request.user
    if es_personal:
        clientes = Persona.objects.filter(rol='cliente', is_active=True).order_by('first_name', 'last_name')
        dueno = None

    if request.method == 'POST':
        if es_personal:
            dueno = Persona.objects.filter(id=request.POST.get('dueno_id') or None, rol='cliente').first()

        form = MascotaForm(request.POST, request.FILES, sin_cuenta=dueno is None)

        if form.is_valid():
            mascota = form.save(commit=False)
            mascota.dueno = dueno
            if dueno is not None:
                mascota.nombre_dueno = ''
                mascota.rut_dueno = ''
            mascota.save()
            messages.success(request, 'Mascota agregada correctamente.')
            if es_personal:
                return redirect('pacientes')
            return redirect('dashboard')
    else:
        form = MascotaForm()

    context = {
        'form': form,
        'clientes': clientes,
        'dueno_elegido': dueno,
    }
    return render(request, 'citas/agregar_mascota_form.html', context)


def agendar_view(request):
    if request.user.is_authenticated:
        mascotas = Mascota.objects.filter(dueno=request.user)
    else:
        mascotas = []
    fecha_param = request.GET.get('fecha') or request.POST.get('fecha')
    mascota_id = request.GET.get('mascota_id') or request.POST.get('mascota_id')

    try:
        fecha_seleccionada = datetime.strptime(str(fecha_param), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha_seleccionada = timezone.localdate()

    mascota_elegida = None
    if mascota_id and request.user.is_authenticated:
        mascota_elegida = Mascota.objects.filter(id=mascota_id, dueno=request.user).first()

    # solo escondemos los datos de contacto si la cuenta ya los tiene
    # completos si falta alguno se muestran para que los complete ahi
    cuenta_completa = bool(
        request.user.is_authenticated
        and request.user.first_name
        and request.user.last_name
        and request.user.telefono
    )

    recargando = request.POST.get('recargar') == '1'

    if request.method == 'POST' and not recargando:
        datos = request.POST.copy()
        if cuenta_completa:
            datos.update({
                'nombre': request.user.first_name,
                'apellido': request.user.last_name,
                'email': request.user.email,
                'telefono': request.user.telefono,
            })
        form = SolicitudCitaForm(datos)
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)
        if form.is_valid():
            solicitud = form.save(commit=False)
            if request.user.is_authenticated:
                solicitud.cliente = request.user
                solicitud.mascota = mascota_elegida
            solicitud.estado = 'Pendiente'
            solicitud.estado_pago = 'Pendiente'
            solicitud.save()

            ids_sesion = request.session.get('mis_solicitudes', [])
            ids_sesion.append(solicitud.id)
            request.session['mis_solicitudes'] = ids_sesion

            return redirect('confirmar_cita', solicitud.id)
    else:
        # si viene de recargar la pagina (por ejemplo al cambiar la fecha)
        # esto rescata lo que la persona ya habia escrito en el formulario
        campos_del_form = [
            'fecha', 'hora', 'nombre', 'apellido', 'email', 'telefono',
            'nombre_mascota', 'especie_mascota', 'raza_mascota', 'sexo_mascota',
            'edad_valor_mascota', 'edad_unidad_mascota', 'tipo_consulta', 'observaciones',
        ]
        if recargando:
            datos_previos = request.POST
        else:
            datos_previos = request.GET

        initial = {}
        for campo in campos_del_form:
            valor = datos_previos.get(campo)
            if valor:
                initial[campo] = valor
        initial['fecha'] = fecha_seleccionada
        if cuenta_completa:
            initial.update({
                'nombre': request.user.first_name,
                'apellido': request.user.last_name,
                'email': request.user.email,
                'telefono': request.user.telefono,
            })
        if mascota_elegida:
            initial.update({
                'nombre_mascota': mascota_elegida.nombre,
                'especie_mascota': mascota_elegida.especie,
                'raza_mascota': mascota_elegida.raza,
                'sexo_mascota': mascota_elegida.sexo,
                'edad_valor_mascota': mascota_elegida.edad_valor,
                'edad_unidad_mascota': mascota_elegida.edad_unidad,
            })
        form = SolicitudCitaForm(initial=initial)
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)

    form.fields['fecha'].widget.attrs['min'] = timezone.localdate().isoformat()

    bloqueos_del_dia = BloqueoHorario.objects.filter(fecha=fecha_seleccionada)

    return render(request, 'citas/agendar_form.html', {
        'form': form,
        'mascotas': mascotas,
        'fecha_seleccionada': fecha_seleccionada,
        'mascota_elegida': mascota_elegida,
        'cuenta_completa': cuenta_completa,
        'bloqueos_del_dia': bloqueos_del_dia,
    })


def confirmar_cita(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404
    return render(request, 'citas/confirmar_cita.html', {'solicitud': solicitud})


def cancelar_solicitud(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404
    solicitud.delete()
    messages.info(request, 'Cancelaste la solicitud de cita.')
    return redirect('agendar')


# WEBPAY

def iniciar_pago_webpay(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404

    if solicitud.estado_pago == 'Pagado':
        messages.info(request, 'Esta cita ya se encuentra pagada.')
        return redirect('reserva_exitosa', solicitud.pk)

    monto = solicitud.tipo_consulta.precio_base

    buy_order = f'cita-{solicitud.pk}-{int(timezone.now().timestamp())}'
    session_id = f'sesion-{solicitud.pk}'

    return_url = request.build_absolute_uri(reverse('retorno_webpay'))

    try:
        tx = get_webpay_transaction()
        response = tx.create(buy_order=buy_order, session_id=session_id, amount=monto, return_url=return_url)
        solicitud.webpay_orden = buy_order
        solicitud.webpay_token = response['token']
        solicitud.save()

        return render(request, 'citas/pago/redirigir_webpay.html', {'url': response['url'], 'token': response['token']})

    except Exception as e:
        messages.error(request, f'Error al iniciar el pago: {e}')
        return redirect('reserva_fallida_id', solicitud.pk)


def marcar_pago_rechazado(solicitud):
    solicitud.estado = 'Cancelada'
    solicitud.estado_pago = 'Rechazado'
    solicitud.save()


def retorno_webpay(request):

    tbk_token = request.GET.get('TBK_TOKEN') or request.POST.get('TBK_TOKEN')
    if tbk_token:
        solicitud = SolicitudCita.objects.filter(webpay_token=tbk_token).first()
        messages.error(request, 'Cancelaste el pago. La cita fue cancelada.')
        if solicitud:
            marcar_pago_rechazado(solicitud)
            return redirect('reserva_fallida_id', solicitud.pk)
        return redirect('reserva_fallida')

    token = request.GET.get('token_ws') or request.POST.get('token_ws')

    if not token:
        messages.error(request, 'No se recibió respuesta de Webpay.')
        return redirect('reserva_fallida')

    # a que cita corresponde el pago
    solicitud = SolicitudCita.objects.filter(webpay_token=token).first()
    if not solicitud:
        messages.error(request, 'No se encontró la solicitud asociada al pago.')
        return redirect('reserva_fallida')

    try:
        tx = get_webpay_transaction()
        # aqui se confirma el pago con webpay, commit(token) le pregunta a
        # webpay si el pago fue aprobado o rechazado
        response = tx.commit(token)
        if response.get('status') == 'AUTHORIZED':
            solicitud.estado = 'Confirmada'
            solicitud.estado_pago = 'Pagado'
            solicitud.monto_pagado = solicitud.tipo_consulta.precio_base
            solicitud.fecha_pago = timezone.now()
            solicitud.save()
            enviar_correo_confirmacion(solicitud)
            messages.success(request, 'Tu cita fue reservada y pagada correctamente.')
            return redirect('reserva_exitosa', solicitud.pk)
        else:
            marcar_pago_rechazado(solicitud)
            messages.error(request, 'El pago no fue aprobado. La cita fue cancelada.')
            return redirect('reserva_fallida_id', solicitud.pk)
    except Exception as e:
        marcar_pago_rechazado(solicitud)
        messages.error(request, f'Error al confirmar el pago: {e}')
        return redirect('reserva_fallida_id', solicitud.pk)


def reserva_exitosa(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404
    return render(request, 'citas/pago/reserva_exitosa.html', {'solicitud': solicitud})


def reserva_fallida(request, id=None):
    solicitud = None
    if id:
        solicitud = get_object_or_404(SolicitudCita, id=id)
        if not puede_ver_solicitud(request, solicitud):
            raise Http404
    return render(request, 'citas/pago/reserva_fallida.html', {'solicitud': solicitud})


MESES_LARGOS = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def primer_dia_del_siguiente_mes(primer_dia):
    if primer_dia.month == 12:
        return date(primer_dia.year + 1, 1, 1)
    return date(primer_dia.year, primer_dia.month + 1, 1)


def rango_de_un_mes(primer_dia):
    primer_dia_siguiente = primer_dia_del_siguiente_mes(primer_dia)
    inicio = rango_del_dia(primer_dia)[0]
    fin = rango_del_dia(primer_dia_siguiente - timedelta(days=1))[1]
    return (inicio, fin)


@never_cache
@login_required(login_url='sin_acceso')
def ingresos_doctora(request):
    if request.user.rol != 'veterinaria':
        return redirect('sin_acceso')

    hoy = timezone.localdate()

    citas_pagadas = SolicitudCita.objects.select_related('tipo_consulta').filter(estado_pago='Pagado')
    citas_pagadas = citas_pagadas.order_by('-fecha_pago')

    primer_dia_mes_actual = hoy.replace(day=1)
    rango_mes_actual = rango_de_un_mes(primer_dia_mes_actual)
    citas_mes_actual = citas_pagadas.filter(fecha_pago__range=rango_mes_actual)

    suma_mes_actual = citas_mes_actual.aggregate(total=Sum('monto_pagado'))['total']
    if suma_mes_actual is None:
        ingresos_mes_actual = 0
    else:
        ingresos_mes_actual = suma_mes_actual

    nombre_mes_actual = MESES_LARGOS[hoy.month - 1]

    context = {
        'citas_pagadas': citas_pagadas[:50],
        'nombre_mes_actual': nombre_mes_actual,
        'ingresos_mes_actual': format(ingresos_mes_actual, ',').replace(',', '.'),
    }
    return render(request, 'citas/ingresos.html', context)

# Ficha medica 
@never_cache
@login_required(login_url='sin_acceso')
def ficha_medica_detalle(request, cita_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    solicitud = get_object_or_404(SolicitudCita, id=cita_id)

    try:
        ficha = solicitud.ficha_medica
    except FichaMedica.DoesNotExist:
        ficha = None

    ahora = timezone.now()
    esta_pagada = solicitud.estado_pago == 'Pagado'
    dia_de_la_cita = timezone.localtime(solicitud.fecha_hora).date()

    puede_llenar_ficha = False
    if esta_pagada and (solicitud.estado == 'Confirmada' or solicitud.estado == 'Finalizado'):
        if dia_de_la_cita <= timezone.localdate():
            puede_llenar_ficha = True

    puede_reagendar = False
    if esta_pagada and solicitud.estado == 'Confirmada' and solicitud.fecha_hora > ahora:
        puede_reagendar = True

    puede_marcar_ausente = False
    if esta_pagada and solicitud.estado == 'Confirmada' and solicitud.fecha_hora <= ahora and ficha is None:
        puede_marcar_ausente = True

    if request.method == 'POST' and not puede_llenar_ficha:
        messages.error(request, 'No se puede registrar la ficha de esta cita.')
        return redirect('ficha_medica_detalle', cita_id=solicitud.id)

    if request.method == 'POST':
        form = FichaMedicaForm(request.POST, instance=ficha)
        if form.is_valid():
            ficha_nueva = form.save(commit=False)
            ficha_nueva.solicitud = solicitud
            ficha_nueva.mascota = solicitud.mascota
            ficha_nueva.especie = solicitud.especie_mascota
            ficha_nueva.raza = solicitud.raza_mascota
            ficha_nueva.sexo = solicitud.sexo_mascota
            ficha_nueva.edad_mascota = solicitud.edad_valor_mascota
            ficha_nueva.save()

            solicitud.estado = 'Finalizado'
            solicitud.save()

            messages.success(request, 'Ficha clínica guardada correctamente.')
            return redirect('agenda_doctora')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = FichaMedicaForm(instance=ficha)

    context = {
        'solicitud': solicitud,
        'mascota': solicitud.mascota,
        'ficha': ficha,
        'form': form,
        'puede_llenar_ficha': puede_llenar_ficha,
        'puede_reagendar': puede_reagendar,
        'puede_marcar_ausente': puede_marcar_ausente,
        'volver_url': reverse('agenda_doctora'),
    }
    return render(request, 'citas/ficha_medica_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def ficha_sin_cita(request, mascota_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    mascota = get_object_or_404(Mascota, id=mascota_id)
    if request.method == 'POST':
        form = FichaMedicaForm(request.POST)
        if form.is_valid():
            ficha_nueva = form.save(commit=False)
            ficha_nueva.mascota = mascota
            ficha_nueva.especie = mascota.especie
            ficha_nueva.raza = mascota.raza
            ficha_nueva.sexo = mascota.sexo
            ficha_nueva.edad_mascota = mascota.edad_valor
            ficha_nueva.save()
            messages.success(request, 'Ficha clínica guardada correctamente.')
            return redirect('pacientes')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = FichaMedicaForm()
    context = {'mascota': mascota, 'form': form, 'volver_url': reverse('pacientes'), 'puede_llenar_ficha': True}
    return render(request, 'citas/ficha_medica_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def fichas_paciente(request, mascota_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    mascota = get_object_or_404(Mascota, id=mascota_id)
    fichas = FichaMedica.objects.filter(mascota=mascota).select_related('solicitud__tipo_consulta')
    context = {'mascota': mascota,'fichas': fichas.order_by('-fecha_atencion'),'cita_sin_ficha': citas_sin_ficha(mascota).first(),}
    return render(request, 'citas/fichas_paciente.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def editar_ficha(request, ficha_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    
    ficha = get_object_or_404(FichaMedica, id=ficha_id)
    if ficha.mascota_id:
        volver_url = reverse('fichas_paciente', args=[ficha.mascota_id])
    else:
        volver_url = reverse('pacientes')

    if request.method == 'POST':
        form = FichaMedicaForm(request.POST, instance=ficha)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ficha clínica actualizada correctamente.')
            return redirect(volver_url)
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = FichaMedicaForm(instance=ficha)
    context = {'solicitud': ficha.solicitud, 'mascota': ficha.mascota, 'ficha': ficha, 'form': form, 'volver_url': volver_url, 'puede_llenar_ficha': True}
    return render(request, 'citas/ficha_medica_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def imprimir_ficha(request, ficha_id):
    ficha = get_object_or_404(FichaMedica, id=ficha_id)
    es_personal = es_personal_clinica(request.user)
    if not es_personal and not (ficha.mascota and ficha.mascota.dueno == request.user):
        return redirect('sin_acceso')
    antecedentes = {'Vacunas': ficha.vacunas,'Alergias': ficha.alergias,'Cirugías previas': ficha.cirugias_previas,'Observaciones': ficha.observaciones,}
    antecedentes = {titulo: texto for titulo, texto in antecedentes.items() if texto}
    return render(request, 'citas/imprimir_ficha.html', {'ficha': ficha, 'antecedentes': antecedentes, 'es_personal': es_personal})

@login_required(login_url='sin_acceso')
def marcar_no_asistio(request, cita_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    if request.method != 'POST':
        return redirect('ficha_medica_detalle', cita_id=cita_id)

    solicitud = get_object_or_404(SolicitudCita, id=cita_id)
    ya_paso = solicitud.fecha_hora <= timezone.now()

    if solicitud.estado == 'Confirmada' and solicitud.estado_pago == 'Pagado' and ya_paso:
        solicitud.estado = 'Ausente'
        solicitud.save()
        messages.success(request, 'La cita quedó marcada como "No asistió".')
    else:
        messages.error(request, 'Esta cita no se puede marcar como "No asistió".')

    return redirect('agenda_doctora')


def enviar_correo_reagendada(solicitud):
    if not solicitud.email:
        return

    fecha = timezone.localtime(solicitud.fecha_hora).strftime('%d/%m/%Y %H:%M')
    asunto = 'Tu cita fue reagendada - Vet Arica'
    mensaje = (
        f'Hola {solicitud.nombre}, tu cita para {solicitud.nombre_mascota} '
        f'quedó para el {fecha}. Te esperamos en Vet Arica.'
    )
    try:
        send_mail(asunto, mensaje, None, [solicitud.email])
    except Exception:
        pass


@never_cache
@login_required(login_url='sin_acceso')
def reagendar_cita(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    es_personal = es_personal_clinica(request.user)

    if es_personal:
        puede = solicitud.estado == 'Confirmada' and solicitud.estado_pago == 'Pagado' and solicitud.fecha_hora > timezone.now()
    else:
        puede = solicitud.cliente_id == request.user.id and solicitud.puede_reagendarse()

    if not puede:
        messages.error(request, 'Esta cita ya no se puede reagendar.')
        if es_personal:
            return redirect('agenda_doctora')
        return redirect('historial_citas')

    fecha_param = request.GET.get('fecha') or request.POST.get('fecha')
    try:
        fecha_seleccionada = datetime.strptime(str(fecha_param), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha_seleccionada = timezone.localtime(solicitud.fecha_hora).date()

    if request.method == 'POST':
        form = ReagendarCitaForm(request.POST)
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)
        if form.is_valid():
            solicitud.fecha_hora = form.fecha_hora
            if not es_personal:
                solicitud.veces_reagendada = solicitud.veces_reagendada + 1
            solicitud.save()
            enviar_correo_reagendada(solicitud)
            messages.success(request, 'La cita fue reagendada correctamente.')
            if es_personal:
                return redirect('agenda_doctora')
            return redirect('historial_citas')
    else:
        form = ReagendarCitaForm(initial={'fecha': fecha_seleccionada})
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)

    context = {
        'form': form,
        'solicitud': solicitud,
        'fecha_seleccionada': fecha_seleccionada,
        'es_personal': es_personal,
    }
    return render(request, 'citas/reagendar_cita.html', context)


def citas_sin_ficha(mascota):
    citas = SolicitudCita.objects.filter(mascota=mascota, estado_pago='Pagado', ficha_medica__isnull=True)
    citas = citas.exclude(estado='Cancelada').exclude(estado='Ausente')
    return citas.order_by('-fecha_hora')


@never_cache
@login_required(login_url='sin_acceso')
def pacientes(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    buscar = request.GET.get('buscar', '').strip()
    mascotas = Mascota.objects.order_by('dueno__first_name', 'nombre')

    if buscar:
        por_mascota = mascotas.filter(nombre__icontains=buscar)
        por_nombre = mascotas.filter(dueno__first_name__icontains=buscar)
        por_apellido = mascotas.filter(dueno__last_name__icontains=buscar)
        por_rut = mascotas.filter(dueno__rut__icontains=buscar)
        por_nombre_sin_cuenta = mascotas.filter(nombre_dueno__icontains=buscar)
        por_rut_sin_cuenta = mascotas.filter(rut_dueno__icontains=buscar)
        mascotas = por_mascota | por_nombre | por_apellido | por_rut | por_nombre_sin_cuenta | por_rut_sin_cuenta

    lista_pacientes = []
    for mascota in mascotas:
        fichas = FichaMedica.objects.filter(mascota=mascota).order_by('-fecha_atencion')
        lista_pacientes.append({
            'mascota': mascota,
            'cantidad_fichas': fichas.count(),
            'ultima_ficha': fichas.first(),
            'cita_sin_ficha': citas_sin_ficha(mascota).first(),
        })

    context = {
        'lista_pacientes': lista_pacientes,
        'buscar': buscar,
    }
    return render(request, 'citas/pacientes.html', context)