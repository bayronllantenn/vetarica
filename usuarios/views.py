from datetime import timedelta

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from citas.forms import BloqueoHorarioForm, HORAS_ATENCION, rango_del_dia, MascotaForm, TipoConsultaForm
from citas.models import BloqueoHorario, FichaMedica, Mascota, SolicitudCita, TipoConsulta
from .forms import ConfiguracionForm, CrearUsuarioForm, EditarUsuarioForm, LoginForm, RegisterForm
from .models import Persona


def es_personal_clinica(usuario):
    return usuario.rol in ('veterinaria', 'secretaria')


def es_veterinaria(usuario):
    return usuario.rol == 'veterinaria'

MESES_ABREVIADOS = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
]


def redirigir_segun_rol(usuario):
    if es_personal_clinica(usuario):
        return redirect('inicio_doctora')
    return redirect('dashboard')


@never_cache
def registro_view(request):
    if request.user.is_authenticated:
        return redirigir_segun_rol(request.user)

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cuenta creada correctamente. Ya puedes iniciar sesión.')
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'usuarios/registro_form.html', {'form': form})


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirigir_segun_rol(request.user)
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)
            messages.success(request, f'Bienvenido, {usuario.first_name} {usuario.last_name}.')
            return redirigir_segun_rol(usuario)
        correo = request.POST.get('username', '').strip()
        clave = request.POST.get('password', '')
        usuario_bloqueado = Persona.objects.filter(email__iexact=correo, is_active=False).first()
        if usuario_bloqueado and usuario_bloqueado.check_password(clave):
            messages.error(request, 'Tu cuenta fue bloqueada. Comunícate con la veterinaria.')
        else:
            messages.error(request, 'Correo electrónico o contraseña incorrectos.')
    else:
        form = LoginForm()
    return render(request, 'usuarios/login_form.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente.')
    return redirect('home')


def sin_acceso_view(request):
    return render(request, 'usuarios/autorizacion/error.html')


@never_cache
@login_required(login_url='sin_acceso')
def dashboard_usuario(request):
    ahora = timezone.now()
    citas = request.user.citas_solicitadas.all()
    citas = citas.order_by('-fecha_hora')
    mascotas = request.user.mascotas.all()

    mascotas_info = []
    for mascota in mascotas:
        fichas_mascota = FichaMedica.objects.filter(solicitud__mascota=mascota)
        fichas_mascota = fichas_mascota.order_by('-fecha_atencion')
        ultima_ficha = fichas_mascota.first()
        mascotas_info.append({
            'mascota': mascota,
            'ultima_ficha': ultima_ficha,
        })

    proximas_citas = request.user.citas_solicitadas.filter(fecha_hora__gte=ahora)
    proximas_citas = proximas_citas.exclude(estado__iexact='cancelada')
    proximas_citas = proximas_citas.order_by('fecha_hora')
    proxima_cita = proximas_citas.first()

    citas_del_anio = request.user.citas_solicitadas.filter(fecha_hora__year=ahora.year, fecha_hora__lt=ahora)
    citas_del_anio = citas_del_anio.exclude(estado__iexact='cancelada')
    citas_anio = citas_del_anio.count()

    context = {
        'citas': citas,
        'mascotas': mascotas,
        'mascotas_info': mascotas_info,
        'proxima_cita': proxima_cita,
        'citas_anio': citas_anio,
    }
    return render(request, 'usuarios/cliente/dashboard.html', context)


@never_cache
@login_required(login_url='sin_acceso')
def inicio_doctora(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    hoy = timezone.localdate()

    # citas de hoy sin las canceladas ordenadas por hora
    rango_hoy = rango_del_dia(hoy)
    citas_hoy = SolicitudCita.objects.select_related('tipo_consulta').filter(fecha_hora__range=rango_hoy)
    citas_hoy = citas_hoy.exclude(estado__iexact='cancelada')
    citas_hoy = citas_hoy.order_by('fecha_hora')

    # marcamos cual cita ya paso y cual es la siguiente por venir, para destacarla en la lista
    ahora = timezone.now()
    ya_eligio_la_siguiente = False
    citas_hoy_info = []
    for cita in citas_hoy:
        ya_paso = cita.fecha_hora < ahora
        es_siguiente = False
        if not ya_paso and not ya_eligio_la_siguiente:
            es_siguiente = True
            ya_eligio_la_siguiente = True
        citas_hoy_info.append({
            'cita': cita,
            'ya_paso': ya_paso,
            'es_siguiente': es_siguiente,
        })

    # suma de lo pagado desde el dia 1 de este mes
    inicio_mes_dt = rango_del_dia(hoy.replace(day=1))[0]
    pagos_del_mes = SolicitudCita.objects.filter(estado_pago='Pagado', fecha_pago__gte=inicio_mes_dt)
    suma_pagos_mes = pagos_del_mes.aggregate(total=Sum('monto_pagado'))['total']
    if suma_pagos_mes is None:
        ingresos_mes = 0
    else:
        ingresos_mes = suma_pagos_mes

    ingresos_mes = format(ingresos_mes, ',').replace(',', '.')

    tipos_consulta = TipoConsulta.objects.all()

    context = {
        'citas_hoy': citas_hoy,
        'citas_hoy_info': citas_hoy_info,
        'ingresos_mes': ingresos_mes,
        'tipos_consulta': tipos_consulta,
    }
    return render(request, 'usuarios/doctora/inicio.html', context)


@never_cache
@login_required(login_url='sin_acceso')
def agenda_doctora(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    try:
        semanas = int(request.GET.get('semana', 0))
    except ValueError:
        semanas = 0

    hoy = timezone.localdate()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    lunes_semana = lunes_actual + timedelta(weeks=semanas)

    dias_semana = []
    for i in range(6):
        dias_semana.append(lunes_semana + timedelta(days=i))

    horas = []
    for hora, _ in HORAS_ATENCION:
        if hora:
            horas.append(hora)

    primer_dia_semana = dias_semana[0]
    ultimo_dia_semana = dias_semana[5]
    inicio_semana = rango_del_dia(primer_dia_semana)[0]
    fin_semana = rango_del_dia(ultimo_dia_semana)[1]
    rango_semana = (inicio_semana, fin_semana)

    citas_semana = SolicitudCita.objects.select_related('tipo_consulta').filter(fecha_hora__range=rango_semana)
    citas_semana = citas_semana.exclude(estado__iexact='cancelada')

    citas_por_dia_hora = {}
    for cita in citas_semana:
        hora_local = timezone.localtime(cita.fecha_hora)
        hora_texto = hora_local.strftime('%H:%M')
        clave = (hora_local.date(), hora_texto)
        citas_por_dia_hora[clave] = cita

    dias_semana_info = []
    for dia in dias_semana:
        if dia == hoy:
            es_hoy = True
        else:
            es_hoy = False
        dias_semana_info.append({
            'fecha': dia,
            'es_hoy': es_hoy,
        })

    filas = []
    for hora in horas:
        celdas = []
        for dia in dias_semana:
            celdas.append({
                'cita': citas_por_dia_hora.get((dia, hora)),
            })

        filas.append({
            'hora': hora,
            'celdas': celdas,
        })

    mes_inicio = MESES_ABREVIADOS[primer_dia_semana.month - 1]
    mes_fin = MESES_ABREVIADOS[ultimo_dia_semana.month - 1]
    if primer_dia_semana.month == ultimo_dia_semana.month:
        subtitulo_semana = f'{primer_dia_semana.day} al {ultimo_dia_semana.day} {mes_fin} {ultimo_dia_semana.year}'
    else:
        subtitulo_semana = f'{primer_dia_semana.day} {mes_inicio} - {ultimo_dia_semana.day} {mes_fin} {ultimo_dia_semana.year}'

    if semanas == 0:
        es_semana_actual = True
    else:
        es_semana_actual = False

    context = {
        'dias_semana': dias_semana_info,
        'filas': filas,
        'total_citas': len(citas_por_dia_hora),
        'subtitulo_semana': subtitulo_semana,
        'es_semana_actual': es_semana_actual,
        'semana_anterior': semanas - 1,
        'semana_siguiente': semanas + 1,
    }
    return render(request, 'usuarios/doctora/agenda.html', context)

#muestra la lista de usuarios que estan creados
@never_cache
@login_required(login_url='sin_acceso')
def usuarios_list(request):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')

    buscar = request.GET.get('buscar', '')
    usuarios = Persona.objects.order_by('rol', 'first_name')
    if buscar:
        por_nombre = usuarios.filter(first_name__icontains=buscar)
        por_apellido = usuarios.filter(last_name__icontains=buscar)
        por_correo = usuarios.filter(email__icontains=buscar)
        por_rut = usuarios.filter(rut__icontains=buscar)
        usuarios = por_nombre | por_apellido | por_correo | por_rut

    context = {
        'usuarios': usuarios,
        'buscar': buscar,
    }
    return render(request, 'usuarios/doctora/usuarios_list.html', context)

@never_cache
@login_required(login_url='sin_acceso')
#esta funcion permite crear el usuario desde la doctora en usuarios_list.html
def crear_usuario(request):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = CrearUsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f'Usuario {usuario.email} creado correctamente.')
            return redirect('usuarios_list')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = CrearUsuarioForm()
    context = {
        'form': form,
        'titulo': 'Crear usuario',
        'texto_boton': 'Crear usuario',
    }
    return render(request, 'usuarios/doctora/usuario_form.html', context)
#aqui se puede editar el usuario desde la doctora 
@never_cache
@login_required(login_url='sin_acceso')
def editar_usuario(request, usuario_id):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    usuario = get_object_or_404(Persona, id=usuario_id)
    if usuario == request.user:
        messages.error(request, 'No puedes editar tu propia cuenta desde aquí.')
        return redirect('usuarios_list')

    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f'Los datos de {usuario.email} se guardaron correctamente.')
            return redirect('usuarios_list')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = EditarUsuarioForm(instance=usuario)
    context = {
        'form': form,
        'titulo': 'Editar usuario',
        'texto_boton': 'Guardar cambios',
    }
    return render(request, 'usuarios/doctora/usuario_form.html', context)
# esto nos permite bloquear el usuario 
@login_required(login_url='sin_acceso')
def bloquear_usuario(request, usuario_id):
    if not es_veterinaria(request.user):
        return redirect('sin_acceso')
    usuario = get_object_or_404(Persona, id=usuario_id)
    if request.method == 'POST':
        if usuario == request.user:
            messages.error(request, 'No puedes bloquear tu propia cuenta.')
        elif usuario.is_active:
            usuario.is_active = False
            usuario.save()
            messages.success(request, f'{usuario.email} fue bloqueado y ya no puede iniciar sesión.')
        else:
            usuario.is_active = True
            usuario.save()
            messages.success(request, f'{usuario.email} fue desbloqueado.')
    return redirect('usuarios_list')

@never_cache
@login_required(login_url='sin_acceso')
def bloqueos_doctora(request):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    if request.method == 'POST':
        form = BloqueoHorarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Horario bloqueado correctamente.')
            return redirect('bloqueos_doctora')
        messages.error(request, 'Revisa los campos marcados en rojo.')
    else:
        form = BloqueoHorarioForm()

    hoy = timezone.localdate()
    form.fields['fecha'].widget.attrs['min'] = hoy.isoformat()

    bloqueos = BloqueoHorario.objects.filter(fecha__gte=hoy)
    bloqueos = bloqueos.order_by('fecha', 'hora_inicio')

    context = {
        'form': form,
        'bloqueos': bloqueos,
    }
    return render(request, 'usuarios/doctora/bloqueos.html', context)


@login_required(login_url='sin_acceso')
def eliminar_bloqueo(request, bloqueo_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    bloqueo = get_object_or_404(BloqueoHorario, id=bloqueo_id)
    if request.method == 'POST':
        bloqueo.delete()
        messages.success(request, 'Bloqueo eliminado correctamente.')
    return redirect('bloqueos_doctora')


@never_cache
@login_required(login_url='sin_acceso')
def historial_citas(request):
    anio_actual = timezone.now().year
    citas = request.user.citas_solicitadas.select_related('mascota')
    citas = citas.order_by('-fecha_hora')

    periodo = request.GET.get('periodo', 'este_ano')
    mascota_sel = request.GET.get('mascota', '')
    estado_sel = request.GET.get('estado', '')

    if periodo == 'este_ano':
        citas = citas.filter(fecha_hora__year=anio_actual)
    elif periodo == 'ano_pasado':
        citas = citas.filter(fecha_hora__year=anio_actual - 1)

    if mascota_sel:
        citas = citas.filter(mascota_id=mascota_sel)
    if estado_sel:
        citas = citas.filter(estado=estado_sel)

    estados = SolicitudCita.ESTADOS

    paginador = Paginator(citas, 8)
    numero_pagina = request.GET.get('page')
    page_obj = paginador.get_page(numero_pagina)

    context = {
        'page_obj': page_obj,
        'mascotas': request.user.mascotas.all(),
        'estados': estados,
        'periodo': periodo,
        'mascota_sel': mascota_sel,
        'estado_sel': estado_sel,
    }
    return render(request, 'usuarios/cliente/historial_citas_list.html', context)

@login_required(login_url='sin_acceso')
def ficha_mascota(request, mascota_id):
    mascota = get_object_or_404(Mascota, id=mascota_id, dueno=request.user)
    historial = FichaMedica.objects.filter(solicitud__mascota=mascota)
    historial = historial.order_by('-fecha_atencion')
    context = {
        'mascota': mascota,
        'historial': historial,
    }
    return render(request, 'usuarios/cliente/ficha_mascota.html', context)


@login_required
def configuracion(request):
    if request.method == "POST":
        form = ConfiguracionForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Tus cambios se guardaron correctamente.")
            return redirect("dashboard")
        messages.error(request, "Revisa los campos marcados en rojo.")
    else:
        form = ConfiguracionForm(instance=request.user)

    return render(request, "usuarios/cliente/configuracion.html", {"form": form})

@login_required(login_url='sin_acceso')
def eliminar_mascota(request, mascota_id):
    mascota = get_object_or_404(Mascota, id=mascota_id, dueno=request.user)
    if request.method == 'POST':
        mascota.delete()
        messages.success(request, f'{mascota.nombre} fue eliminada correctamente.')
    return redirect('dashboard')

@login_required(login_url='sin_acceso')
def editar_mascota(request, mascota_id):
    mascota = get_object_or_404(Mascota, id=mascota_id, dueno=request.user)
    if request.method == 'POST':
        form = MascotaForm(request.POST, request.FILES, instance=mascota)
        if form.is_valid():
            form.save()
            messages.success(request, f'{mascota.nombre} fue actualizada correctamente.')
            return redirect('dashboard')
    else:
        form = MascotaForm(instance=mascota)
    return render(request, 'usuarios/cliente/editar_mascota.html', {'form': form, 'mascota': mascota})

@login_required(login_url='sin_acceso')
def editar_tipo_consulta(request, tipo_id):
    if not es_personal_clinica(request.user):
        return redirect('sin_acceso')

    tipo = get_object_or_404(TipoConsulta, id=tipo_id)
    if request.method == 'POST':
        form = TipoConsultaForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, f'{tipo.nombre} fue actualizado correctamente.')
            return redirect('inicio_doctora')
    else:
        form = TipoConsultaForm(instance=tipo)
    return render(request, 'usuarios/doctora/editar_tipo_consulta.html', {'form': form, 'tipo': tipo})