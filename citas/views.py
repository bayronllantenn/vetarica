from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from usuarios.models import Persona
from usuarios.views import es_personal_clinica
from .forms import CitaInternaForm, FichaMedicaForm, MascotaForm, ReagendarCitaForm, SolicitudCitaForm, cancelar_citas_vencidas, obtener_horas_disponibles, rango_del_dia
from .models import BloqueoHorario, FichaMedica, Mascota, SolicitudCita
from .utils import get_webpay_transaction

def puede_ver_solicitud(request, solicitud):
    if solicitud.cliente_id:
        if request.user.is_authenticated and request.user.id == solicitud.cliente_id:
            return True
        return False

    if solicitud.id in request.session.get('mis_solicitudes', []):
        return True
    return False


def leer_dato(request, nombre):
    valor = request.GET.get(nombre)
    if not valor:
        valor = request.POST.get(nombre)
    return valor


def leer_fecha(texto):
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


def enviar_correo_confirmacion(solicitud):
    if not solicitud.email:
        return

    fecha = timezone.localtime(solicitud.fecha_hora).strftime('%d/%m/%Y %H:%M')
    # separa los miles con punto, ej: 25000 -> 25.000
    monto = format(solicitud.monto_pagado, ',').replace(',', '.')
    asunto = 'Comprobante de pago - Vet Arica'
    mensaje = (
        f'Hola {solicitud.nombre}, tu hora ha sido agendada con éxito.\n\n'
        f'Mascota: {solicitud.nombre_mascota}\n'
        f'Fecha y hora: {fecha}\n'
        f'Servicio: {solicitud.tipo_consulta.nombre}\n'
        f'Monto pagado: ${monto}\n\n'
        f'Gracias por atenderte con nosotros.\n\n'
        f'Atte. Vet Arica'
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
            dueno = None
            dueno_id = request.POST.get('dueno_id', '')
            if dueno_id.isdigit():
                dueno = Persona.objects.filter(id=dueno_id, rol='cliente').first()

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
    fecha_seleccionada = leer_fecha(leer_dato(request, 'fecha'))
    if fecha_seleccionada is None:
        fecha_seleccionada = timezone.localdate()

    mascota_elegida = None
    mascota_id = leer_dato(request, 'mascota_id')
    if mascota_id and mascota_id.isdigit() and request.user.is_authenticated:
        mascota_elegida = Mascota.objects.filter(id=mascota_id, dueno=request.user).first()

    # solo escondemos los datos de contacto si la cuenta ya los tiene
    # completos si falta alguno se muestran para que los complete ahi
    cuenta_completa = False
    if request.user.is_authenticated:
        if request.user.first_name and request.user.last_name and request.user.telefono:
            cuenta_completa = True

    recargando = request.POST.get('recargar') == '1'

    if request.method == 'POST' and not recargando:
        datos = request.POST.copy()
        if cuenta_completa:
            datos['nombre'] = request.user.first_name
            datos['apellido'] = request.user.last_name
            datos['email'] = request.user.email
            datos['telefono'] = request.user.telefono
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
            initial['nombre'] = request.user.first_name
            initial['apellido'] = request.user.last_name
            initial['email'] = request.user.email
            initial['telefono'] = request.user.telefono
        if mascota_elegida:
            initial['nombre_mascota'] = mascota_elegida.nombre
            initial['especie_mascota'] = mascota_elegida.especie
            initial['raza_mascota'] = mascota_elegida.raza
            initial['sexo_mascota'] = mascota_elegida.sexo
            initial['edad_valor_mascota'] = mascota_elegida.edad_valor
            initial['edad_unidad_mascota'] = mascota_elegida.edad_unidad
        form = SolicitudCitaForm(initial=initial)
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)

    form.fields['fecha'].widget.attrs['min'] = timezone.localdate().isoformat()

    bloqueos_del_dia = BloqueoHorario.objects.filter(fecha=fecha_seleccionada)

    context = {'form': form, 'mascotas': mascotas, 'fecha_seleccionada': fecha_seleccionada, 'mascota_elegida': mascota_elegida, 'cuenta_completa': cuenta_completa, 'bloqueos_del_dia': bloqueos_del_dia}
    return render(request, 'citas/cliente/agendar_form.html', context)


def confirmar_cita(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404
    return render(request, 'citas/cliente/confirmar_cita.html', {'solicitud': solicitud})


def cancelar_solicitud(request, id):
    solicitud = get_object_or_404(SolicitudCita, id=id)
    if not puede_ver_solicitud(request, solicitud):
        raise Http404

    if request.method != 'POST':
        return redirect('confirmar_cita', solicitud.id)

    if solicitud.estado_pago == 'Pagado':
        messages.error(request, 'Esta cita ya está pagada y no se puede cancelar aquí.')
        return redirect('confirmar_cita', solicitud.id)

    solicitud.estado = 'Cancelada'
    solicitud.estado_pago = 'Rechazado'
    solicitud.save()
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

    # primero se cancelan las solicitudes que pasaron los 15 minutos sin pagar
    cancelar_citas_vencidas()
    solicitud.refresh_from_db()

    if solicitud.estado == 'Cancelada':
        messages.error(request, 'El tiempo para pagar esta solicitud venció. Agenda nuevamente.')
        return redirect('agendar')

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

    tbk_token = leer_dato(request, 'TBK_TOKEN')
    if tbk_token:
        solicitud = SolicitudCita.objects.filter(webpay_token=tbk_token).first()
        messages.error(request, 'Cancelaste el pago. La cita fue cancelada.')
        if solicitud:
            marcar_pago_rechazado(solicitud)
            return redirect('reserva_fallida_id', solicitud.pk)
        return redirect('reserva_fallida')

    token = leer_dato(request, 'token_ws')

    if not token:
        messages.error(request, 'No se recibió respuesta de Webpay.')
        return redirect('reserva_fallida')

    # a que cita corresponde el pago
    solicitud = SolicitudCita.objects.filter(webpay_token=token).first()
    if not solicitud:
        messages.error(request, 'No se encontró la solicitud asociada al pago.')
        return redirect('reserva_fallida')

    if solicitud.estado_pago == 'Pagado':
        return redirect('reserva_exitosa', solicitud.pk)

    if solicitud.estado == 'Cancelada':
        messages.error(request, 'El tiempo para pagar venció y la hora se liberó. No se realizó ningún cobro.')
        return redirect('reserva_fallida_id', solicitud.pk)

    try:
        tx = get_webpay_transaction()
        # aqui se confirma el pago con webpay, commit(token) le pregunta a
        # webpay si el pago fue aprobado o rechazado
        response = tx.commit(token)
        if response.get('status') == 'AUTHORIZED':
            solicitud.estado = 'Confirmada'
            solicitud.estado_pago = 'Pagado'
            solicitud.monto_pagado = response.get('amount')
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


def sumar_pagos(desde, hasta):
    inicio = rango_del_dia(desde)[0]
    fin = rango_del_dia(hasta)[1]
    citas = SolicitudCita.objects.filter(estado_pago='Pagado', fecha_pago__range=(inicio, fin))

    total = 0
    for cita in citas:
        if cita.monto_pagado:
            total = total + cita.monto_pagado
    return total


@never_cache
@login_required(login_url='sin_acceso')
def ingresos_doctora(request):
    if request.user.rol != 'veterinaria':
        return redirect('sin_acceso')

    hoy = timezone.localdate()
    desde = leer_fecha(request.GET.get('desde'))
    hasta = leer_fecha(request.GET.get('hasta'))
    if desde is None:
        desde = hoy.replace(day=1)
    if hasta is None:
        hasta = hoy
    if desde > hasta:
        messages.error(request, 'La fecha "desde" no puede ser posterior a la fecha "hasta".')
        desde = hoy.replace(day=1)
        hasta = hoy

    inicio = rango_del_dia(desde)[0]
    fin = rango_del_dia(hasta)[1]
    citas_pagadas = SolicitudCita.objects.select_related('tipo_consulta').filter(estado_pago='Pagado', fecha_pago__range=(inicio, fin))
    citas_pagadas = citas_pagadas.order_by('-fecha_pago')

    total = 0
    cantidad = 0
    ingresos_por_mes = {}
    lista_citas = []
    for cita in citas_pagadas:
        monto = 0
        if cita.monto_pagado:
            monto = cita.monto_pagado
        total = total + monto
        cantidad = cantidad + 1

        cita.monto_texto = format(monto, ',').replace(',', '.')
        lista_citas.append(cita)

        mes = timezone.localtime(cita.fecha_pago).strftime('%m/%Y')
        if mes in ingresos_por_mes:
            ingresos_por_mes[mes] = ingresos_por_mes[mes] + monto
        else:
            ingresos_por_mes[mes] = monto

    meses = []
    montos_por_mes = []
    for mes in ingresos_por_mes:
        meses.append(mes)
        montos_por_mes.append(ingresos_por_mes[mes])
    meses.reverse()
    montos_por_mes.reverse()

    promedio = 0
    if cantidad > 0:
        promedio = total // cantidad

    primer_dia_mes = hoy.replace(day=1)
    ultimo_dia_mes_anterior = primer_dia_mes - timedelta(days=1)
    primer_dia_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)

    inicio_trimestre = primer_dia_mes_anterior
    for i in range(2):
        inicio_trimestre = inicio_trimestre - timedelta(days=1)
        inicio_trimestre = inicio_trimestre.replace(day=1)

    total_mes = sumar_pagos(primer_dia_mes, hoy)
    total_mes_anterior = sumar_pagos(primer_dia_mes_anterior, ultimo_dia_mes_anterior)

    sin_ingresos_mes = False
    if total_mes == 0:
        sin_ingresos_mes = True

    diferencia = None
    bajo = False
    if total_mes > 0:
        if total_mes_anterior > 0:
            diferencia = (total_mes - total_mes_anterior) * 100 // total_mes_anterior
            if diferencia < 0:
                bajo = True

    context = {
        'citas_pagadas': lista_citas,
        'desde': desde,
        'hasta': hasta,
        'total': format(total, ',').replace(',', '.'),
        'cantidad': cantidad,
        'promedio': format(promedio, ',').replace(',', '.'),
        'meses': meses,
        'montos_por_mes': montos_por_mes,
        'mes_anterior': primer_dia_mes_anterior,
        'fin_mes_anterior': ultimo_dia_mes_anterior,
        'inicio_trimestre': inicio_trimestre,
        'total_mes': format(total_mes, ',').replace(',', '.'),
        'diferencia': diferencia,
        'bajo': bajo,
        'sin_ingresos_mes': sin_ingresos_mes,
    }
    return render(request, 'citas/doctora/ingresos.html', context)

# Ficha medica 
@never_cache
@login_required(login_url='sin_acceso')
def ficha_medica_detalle(request, cita_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    solicitud = get_object_or_404(SolicitudCita, id=cita_id)

    ficha = FichaMedica.objects.filter(solicitud=solicitud).first()

    ahora = timezone.now()
    esta_pagada = solicitud.estado_pago == 'Pagado'
    paga_en_clinica = solicitud.estado_pago == 'En clinica'
    dia_de_la_cita = timezone.localtime(solicitud.fecha_hora).date()

    puede_llenar_ficha = False
    if esta_pagada or paga_en_clinica:
        if solicitud.estado == 'Confirmada' or solicitud.estado == 'Finalizado':
            if dia_de_la_cita <= timezone.localdate():
                puede_llenar_ficha = True

    puede_reagendar = False
    if esta_pagada and solicitud.estado == 'Confirmada' and solicitud.fecha_hora > ahora:
        puede_reagendar = True

    puede_marcar_ausente = False
    if (esta_pagada or paga_en_clinica) and solicitud.estado == 'Confirmada' and solicitud.fecha_hora <= ahora and ficha is None:
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
    return render(request, 'citas/doctora/ficha_medica_form.html', context)

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
    return render(request, 'citas/doctora/ficha_medica_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def fichas_paciente(request, mascota_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    mascota = get_object_or_404(Mascota, id=mascota_id)
    fichas = FichaMedica.objects.filter(mascota=mascota).select_related('solicitud__tipo_consulta')
    context = {'mascota': mascota, 'fichas': fichas.order_by('-fecha_atencion'), 'cita_sin_ficha': citas_sin_ficha(mascota).first()}
    return render(request, 'citas/doctora/fichas_paciente.html', context)

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
    return render(request, 'citas/doctora/ficha_medica_form.html', context)

@never_cache
@login_required(login_url='sin_acceso')
def imprimir_ficha(request, ficha_id):
    ficha = get_object_or_404(FichaMedica, id=ficha_id)
    es_personal = es_personal_clinica(request.user)
    es_dueno = False
    if ficha.mascota and ficha.mascota.dueno == request.user:
        es_dueno = True
    if not es_personal and not es_dueno:
        return redirect('sin_acceso')

    antecedentes = {}
    if ficha.vacunas:
        antecedentes['Vacunas'] = ficha.vacunas
    if ficha.alergias:
        antecedentes['Alergias'] = ficha.alergias
    if ficha.cirugias_previas:
        antecedentes['Cirugías previas'] = ficha.cirugias_previas
    if ficha.observaciones:
        antecedentes['Observaciones'] = ficha.observaciones

    context = {'ficha': ficha, 'antecedentes': antecedentes, 'es_personal': es_personal}
    return render(request, 'citas/imprimir_ficha.html', context)

@login_required(login_url='sin_acceso')
def marcar_no_asistio(request, cita_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')
    if request.method != 'POST':
        return redirect('ficha_medica_detalle', cita_id=cita_id)

    solicitud = get_object_or_404(SolicitudCita, id=cita_id)
    ya_paso = solicitud.fecha_hora <= timezone.now()
    esta_pagada = solicitud.estado_pago == 'Pagado' or solicitud.estado_pago == 'En clinica'

    if solicitud.estado == 'Confirmada' and esta_pagada and ya_paso:
        solicitud.estado = 'Ausente'
        solicitud.save()
        solicitud.bloqueos.all().delete()
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

    fecha_seleccionada = leer_fecha(leer_dato(request, 'fecha'))
    if fecha_seleccionada is None:
        fecha_seleccionada = timezone.localtime(solicitud.fecha_hora).date()

    if request.method == 'POST':
        form = ReagendarCitaForm(request.POST)
        form.fields['hora'].choices = obtener_horas_disponibles(fecha_seleccionada)
        if form.is_valid():
            solicitud.fecha_hora = form.fecha_hora
            solicitud.recordatorio_enviado = False
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
    citas = SolicitudCita.objects.filter(mascota=mascota, estado_pago__in=['Pagado', 'En clinica'], ficha_medica__isnull=True)
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
    return render(request, 'citas/doctora/pacientes.html', context)


def copiar_datos_de_mascota(solicitud, mascota):
    solicitud.mascota = mascota
    solicitud.nombre_mascota = mascota.nombre
    solicitud.especie_mascota = mascota.especie
    solicitud.raza_mascota = mascota.raza
    solicitud.sexo_mascota = mascota.sexo
    solicitud.edad_valor_mascota = mascota.edad_valor
    solicitud.edad_unidad_mascota = mascota.edad_unidad

    if mascota.dueno:
        solicitud.cliente = mascota.dueno
        solicitud.nombre = mascota.dueno.first_name
        solicitud.apellido = mascota.dueno.last_name
        solicitud.email = mascota.dueno.email
        solicitud.telefono = mascota.dueno.telefono
    else:
        solicitud.nombre = mascota.nombre_dueno


def buscar_mascotas(buscar):
    mascotas = Mascota.objects.select_related('dueno').order_by('nombre')
    por_mascota = mascotas.filter(nombre__icontains=buscar)
    por_nombre = mascotas.filter(dueno__first_name__icontains=buscar)
    por_apellido = mascotas.filter(dueno__last_name__icontains=buscar)
    por_rut = mascotas.filter(dueno__rut__icontains=buscar)
    por_nombre_sin_cuenta = mascotas.filter(nombre_dueno__icontains=buscar)
    por_rut_sin_cuenta = mascotas.filter(rut_dueno__icontains=buscar)
    return por_mascota | por_nombre | por_apellido | por_rut | por_nombre_sin_cuenta | por_rut_sin_cuenta


@never_cache
@login_required(login_url='sin_acceso')
def crear_cita_interna(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        buscar = request.POST.get('buscar', '').strip()
        form = CitaInternaForm(request.POST)
        if form.is_valid():
            solicitud = form.save(commit=False)
            mascota = form.cleaned_data['mascota']
            if mascota:
                copiar_datos_de_mascota(solicitud, mascota)
            solicitud.estado = 'Confirmada'
            solicitud.estado_pago = 'En clinica'
            solicitud.save()

            bloqueo = BloqueoHorario()
            bloqueo.fecha = form.cleaned_data['fecha']
            bloqueo.hora_inicio = form.cleaned_data['hora_inicio']
            bloqueo.hora_fin = form.cleaned_data['hora_fin']
            bloqueo.motivo = f'Cita interna: {solicitud.nombre_mascota}'
            bloqueo.cita = solicitud
            bloqueo.save()

            messages.success(request, 'Cita agendada y horario bloqueado correctamente.')
            return redirect('agenda_doctora')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        buscar = request.GET.get('buscar', '').strip()
        form = CitaInternaForm()

    if buscar:
        form.fields['mascota'].queryset = buscar_mascotas(buscar)
    else:
        form.fields['mascota'].queryset = Mascota.objects.none()

    form.fields['fecha'].widget.attrs['min'] = timezone.localdate().isoformat()
    return render(request, 'citas/doctora/cita_interna_form.html', {'form': form, 'buscar': buscar})