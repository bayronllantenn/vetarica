from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from usuarios.forms import validar_rut
from .models import (ESPECIES_MASCOTA,SEXOS_MASCOTA, UNIDADES_EDAD_MASCOTA,BloqueoHorario,FichaMedica,Mascota,SolicitudCita,TipoConsulta,)

DOMINIOS_CONOCIDOS = {
    'gmail': ['gmail.com'],
    'hotmail': ['hotmail.com', 'hotmail.cl', 'hotmail.es'],
    'outlook': ['outlook.com', 'outlook.cl', 'outlook.es'],
    'yahoo': ['yahoo.com', 'yahoo.cl', 'yahoo.es'],
}

HORAS_ATENCION = [
    ('', 'Selecciona una hora'),
    ('11:00', '11:00'), ('11:30', '11:30'),
    ('12:00', '12:00'), ('12:30', '12:30'),
    ('13:00', '13:00'), ('13:30', '13:30'),
    ('17:00', '17:00'), ('17:30', '17:30'),
    ('18:00', '18:00'), ('18:30', '18:30'),
    ('19:00', '19:00'), ('19:30', '19:30'),
    ('20:00', '20:00'), ('20:30', '20:30'),
]

MINUTOS_PARA_PAGAR = 15
MINUTOS_ANTICIPACION_MINIMA = 60


def cancelar_citas_vencidas():
    # si ya paso el tiempo para pagar y el cliente nunca pago la cita se cancela sola
    limite = timezone.now() - timedelta(minutes=MINUTOS_PARA_PAGAR)
    SolicitudCita.objects.filter(estado_pago='Pendiente', fecha_creacion__lt=limite).update(
        estado='Cancelada', estado_pago='Rechazado'
    )


def rango_del_dia(fecha):
    inicio = datetime.combine(fecha, datetime.min.time())
    fin = datetime.combine(fecha, datetime.max.time())
    inicio = timezone.make_aware(inicio)
    fin = timezone.make_aware(fin)
    return inicio, fin


def citas_que_bloquean():
    cancelar_citas_vencidas()

    # las citas pendientes que todavia estan a tiempo de pagarse tambien
    # cuentan como ocupadas para que nadie mas agende esa misma hora
    citas = SolicitudCita.objects.filter(estado_pago__in=['Pagado', 'Pendiente'])

    # si alguien cancela una cita a mano desde el admin, esa hora se libera
    # de nuevo, aunque el pago haya quedado marcado como pagado
    return citas.exclude(estado='Cancelada')


def obtener_horas_disponibles(fecha):
    # los sabados y domingos no se atiende en la clinica, asi que no hay horas para elegir
    if fecha.weekday() == 5 or fecha.weekday() == 6:
        return [('', 'Selecciona una hora')]

    citas = citas_que_bloquean().filter(fecha_hora__range=rango_del_dia(fecha))
    horas_ocupadas = []
    for c in citas:
        horas_ocupadas.append(timezone.localtime(c.fecha_hora).strftime('%H:%M'))

    # las horas que la doctora bloqueo ese dia tambien cuentan como ocupadas
    bloqueos = BloqueoHorario.objects.filter(fecha=fecha)
    for bloqueo in bloqueos:
        for opcion in HORAS_ATENCION:
            hora = opcion[0]
            if hora:
                si_esta_en_el_bloqueo = hora >= bloqueo.hora_inicio and hora < bloqueo.hora_fin
                if si_esta_en_el_bloqueo:
                    horas_ocupadas.append(hora)

    if fecha == timezone.localdate():
        hora_actual = timezone.localtime().strftime('%H:%M')
    else:
        hora_actual = '00:00'

    horas_disponibles = []
    for opcion in HORAS_ATENCION:
        hora = opcion[0]
        si_esta_libre = hora not in horas_ocupadas and hora > hora_actual
        if not hora or si_esta_libre:
            horas_disponibles.append(opcion)
    return horas_disponibles


def validar_fecha_cita(fecha):
    hoy = timezone.localdate()

    if fecha < hoy:
        raise forms.ValidationError('No puedes agendar en una fecha pasada.')
    if fecha.weekday() == 5:
        raise forms.ValidationError('Los sábados solo atendemos a domicilio.')
    if fecha.weekday() == 6:
        raise forms.ValidationError('No atendemos los domingos.')
    if fecha > hoy + timedelta(days=60):
        raise forms.ValidationError('Solo puedes agendar hasta 60 días hacia adelante.')

    return fecha


def revisar_horario(fecha, hora):
    hora_elegida = datetime.strptime(hora, '%H:%M').time()
    fecha_hora = timezone.make_aware(datetime.combine(fecha, hora_elegida))

    if fecha_hora < timezone.now() + timedelta(minutes=MINUTOS_ANTICIPACION_MINIMA):
        return fecha_hora, 'Elige un horario con al menos 1 hora de anticipación.'
    if citas_que_bloquean().filter(fecha_hora=fecha_hora).exists():
        return fecha_hora, 'Ese horario ya está ocupado, elige otro.'
    if BloqueoHorario.objects.filter(fecha=fecha, hora_inicio__lte=hora, hora_fin__gt=hora).exists():
        return fecha_hora, 'La doctora no atiende en ese horario, elige otro.'

    return fecha_hora, None


def validar_edad(valor, unidad):
    if valor <= 0:
        return 'La edad debe ser mayor a 0.'

    if unidad == 'años':
        limite = 40
    else:
        limite = 480
    if valor > limite:
        return f'Esa edad no parece real estando en {unidad}.'

    return None


def validar_nombre(valor, etiqueta, minimo=2, maximo=40):
    valor = ' '.join(valor.split())

    if len(valor) < minimo:
        raise forms.ValidationError(f'{etiqueta} debe tener al menos {minimo} letras.')
    if len(valor) > maximo:
        raise forms.ValidationError(f'{etiqueta} no puede superar los {maximo} caracteres.')
    if not valor.replace(' ', '').isalpha():
        raise forms.ValidationError(f'{etiqueta} solo puede contener letras.')

    return valor.title()


class SolicitudCitaForm(forms.ModelForm):
    fecha = forms.DateField(
        label='Fecha',
        widget=forms.DateInput(attrs={'type': 'date', 'onchange': 'recargarFormulario(this.form)'}, format='%Y-%m-%d'),
        error_messages={'required': 'Elige una fecha.'},
    )
    hora = forms.ChoiceField(
        label='Hora',
        choices=HORAS_ATENCION,
        error_messages={'required': 'Elige una hora.'},
    )
    tipo_consulta = forms.ModelChoiceField(
        queryset=TipoConsulta.objects.all(),
        empty_label=None,
        error_messages={'required': 'Elige un tipo de consulta.'},
    )
    especie_mascota = forms.ChoiceField(
        label='Especie',
        choices=[('', 'Especie de tu mascota')] + ESPECIES_MASCOTA,
        error_messages={'required': 'Elige la especie de tu mascota.'},
    )
    sexo_mascota = forms.ChoiceField(
        label='Sexo',
        choices=[('', 'Sexo de tu mascota')] + SEXOS_MASCOTA,
        error_messages={'required': 'Elige el sexo de tu mascota.'},
    )
    edad_unidad_mascota = forms.ChoiceField(
        label='Unidad',
        choices=UNIDADES_EDAD_MASCOTA,
        required=False,
        initial='años',
    )

    class Meta:
        model = SolicitudCita
        fields = [
            'nombre',
            'apellido',
            'email',
            'telefono',
            'nombre_mascota',
            'especie_mascota',
            'raza_mascota',
            'sexo_mascota',
            'edad_valor_mascota',
            'edad_unidad_mascota',
            'tipo_consulta',
            'observaciones',
        ]
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'nombre@gmail.com'}),
            'telefono': forms.TextInput(attrs={
                'placeholder': '912345678',
                'inputmode': 'numeric',
                'pattern': '[0-9]{9}',
                'maxlength': '9',
                'title': 'Ingresa 9 números, ej: 912345678',
            }),
            'raza_mascota': forms.TextInput(attrs={'placeholder': 'Raza (opcional)'}),
            'edad_valor_mascota': forms.NumberInput(attrs={'placeholder': 'Edad', 'min': 1}),
            'observaciones': forms.Textarea(attrs={'placeholder': 'Observaciones (opcional)', 'rows': 3}),
        }
        labels = {
            'edad_valor_mascota': 'Edad',
        }

    def clean_nombre(self):
        return validar_nombre(self.cleaned_data['nombre'], 'El nombre')

    def clean_apellido(self):
        return validar_nombre(self.cleaned_data['apellido'], 'El apellido')

    def clean_nombre_mascota(self):
        return validar_nombre(self.cleaned_data['nombre_mascota'], 'El nombre de la mascota')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if '@' not in email:
            raise forms.ValidationError('Ingresa un correo válido, por ejemplo nombre@gmail.com.')

        dominio = email.split('@')[1]
        nombre_dominio = dominio.split('.')[0]

        if nombre_dominio in DOMINIOS_CONOCIDOS and dominio not in DOMINIOS_CONOCIDOS[nombre_dominio]:
            sugerencia = DOMINIOS_CONOCIDOS[nombre_dominio][0]
            raise forms.ValidationError(f'Revisa el correo, ¿es @{sugerencia}?')

        return email

    def clean_telefono(self):
        telefono = self.cleaned_data['telefono'].replace(' ', '')

        if not telefono.isdigit():
            raise forms.ValidationError('El teléfono solo puede contener números.')
        if len(telefono) != 9 or not telefono.startswith('9'):
            raise forms.ValidationError('El teléfono debe tener 9 dígitos y empezar con 9.')

        resto = telefono[1:]
        todos_iguales = resto == resto[0] * 8
        es_seguido = resto == '12345678' or resto == '87654321'
        if todos_iguales or es_seguido:
            raise forms.ValidationError('Ingresa un número de teléfono real.')

        return telefono

    def clean_tipo_consulta(self):
        tipo = self.cleaned_data['tipo_consulta']
        if tipo.precio_base <= 0:
            raise forms.ValidationError('Este tipo de consulta no está disponible.')
        return tipo

    def clean_fecha(self):
        return validar_fecha_cita(self.cleaned_data['fecha'])

    def clean_observaciones(self):
        observaciones = self.cleaned_data.get('observaciones')
        if not observaciones:
            observaciones = ''
        observaciones = ' '.join(observaciones.split())

        if len(observaciones) > 500:
            raise forms.ValidationError('Las observaciones no pueden superar los 500 caracteres.')

        return observaciones

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get('fecha')
        hora = cleaned_data.get('hora')
        edad_valor = cleaned_data.get('edad_valor_mascota')
        edad_unidad = cleaned_data.get('edad_unidad_mascota')

        if edad_valor is not None:
            error = validar_edad(edad_valor, edad_unidad)
            if error:
                self.add_error('edad_valor_mascota', error)

        if fecha and hora:
            fecha_hora, error = revisar_horario(fecha, hora)
            if error:
                self.add_error('hora', error)
            else:
                self.instance.fecha_hora = fecha_hora

        return cleaned_data


class ReagendarCitaForm(forms.Form):
    fecha = forms.DateField(
        label='Nueva fecha',
        widget=forms.DateInput(attrs={'type': 'date', 'onchange': 'recargarFormulario(this.form)'}, format='%Y-%m-%d'),
        error_messages={'required': 'Elige una fecha.'},
    )
    hora = forms.ChoiceField(
        label='Nueva hora',
        choices=HORAS_ATENCION,
        error_messages={'required': 'Elige una hora.'},
    )

    def clean_fecha(self):
        return validar_fecha_cita(self.cleaned_data['fecha'])

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get('fecha')
        hora = cleaned_data.get('hora')

        if fecha and hora:
            fecha_hora, error = revisar_horario(fecha, hora)
            if error:
                self.add_error('hora', error)
            else:
                self.fecha_hora = fecha_hora

        return cleaned_data


class MascotaForm(forms.ModelForm):
    class Meta:
        model = Mascota
        fields = [
            'nombre',
            'especie',
            'raza',
            'sexo',
            'estado_reproductivo',
            'microchip',
            'edad_valor',
            'edad_unidad',
            'imagen',
            'nombre_dueno',
            'rut_dueno',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la mascota', 'maxlength': '40'}),
            'nombre_dueno': forms.TextInput(attrs={'placeholder': 'Nombre y apellido', 'maxlength': '80'}),
            'rut_dueno': forms.TextInput(attrs={'placeholder': 'RUT (ej: 12345678-9)', 'maxlength': '12'}),
            'raza': forms.TextInput(attrs={'placeholder': 'Raza (opcional)'}),
            'microchip': forms.TextInput(attrs={'placeholder': 'Número de microchip (opcional)', 'maxlength': '20'}),
            'edad_valor': forms.NumberInput(attrs={'placeholder': 'Edad', 'min': 0, 'max': 480}),
            'imagen': forms.FileInput(attrs={'accept': 'image/*'}),
        }
        labels = {
            'estado_reproductivo': 'Entero / Castrado',
            'edad_valor': 'Edad',
            'imagen': 'Foto de la mascota (opcional)',
            'nombre_dueno': 'Nombre del dueño',
            'rut_dueno': 'RUT del dueño',
        }

    def __init__(self, data=None, files=None, instance=None, sin_cuenta=False):
        super().__init__(data, files, instance=instance)
        if sin_cuenta:
            self.fields['nombre_dueno'].required = True
            self.fields['nombre_dueno'].error_messages['required'] = 'Escribe el nombre del dueño.'
            self.fields['rut_dueno'].required = True
            self.fields['rut_dueno'].error_messages['required'] = 'Escribe el RUT del dueño.'

    def clean_nombre(self):
        return validar_nombre(self.cleaned_data['nombre'], 'El nombre de la mascota')

    def clean_nombre_dueno(self):
        nombre = self.cleaned_data.get('nombre_dueno', '')
        if nombre:
            return validar_nombre(nombre, 'El nombre del dueño', maximo=80)
        return nombre

    def clean_rut_dueno(self):
        rut = self.cleaned_data.get('rut_dueno', '')
        if rut:
            return validar_rut(rut)
        return rut
    
    def clean_microchip(self):
        microchip = self.cleaned_data.get('microchip', '').replace(' ', '')
        if microchip and not microchip.isdigit():
            raise forms.ValidationError('El microchip solo puede contener números.')
        return microchip

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen and imagen.size > 2 * 1024 * 1024:
            raise forms.ValidationError('La imagen no puede pesar más de 2 MB.')
        return imagen

    def clean(self):
        cleaned_data = super().clean()
        valor = cleaned_data.get('edad_valor')
        unidad = cleaned_data.get('edad_unidad')

        if valor is not None:
            error = validar_edad(valor, unidad)
            if error:
                self.add_error('edad_valor', error)

        return cleaned_data


class FichaMedicaForm(forms.ModelForm):
    class Meta:
        model = FichaMedica
        fields = [
            'peso',
            'temperatura',
            'frecuencia_cardiaca',
            'frecuencia_respiratoria',
            'deshidratacion',
            'tiempo_llenado_capilar',
            'motivo_consulta',
            'diagnostico',
            'tratamiento',
            'vacunas',
            'alergias',
            'cirugias_previas',
            'observaciones',
            'proxima_atencion',
        ]
        widgets = {
            'peso': forms.NumberInput(attrs={'placeholder': 'Peso en kg', 'step': '0.01', 'min': 0}),
            'temperatura': forms.NumberInput(attrs={'placeholder': '°C', 'step': '0.1', 'min': 30, 'max': 45}),
            'frecuencia_cardiaca': forms.NumberInput(attrs={'placeholder': 'latidos por minuto', 'min': 0}),
            'frecuencia_respiratoria': forms.NumberInput(attrs={'placeholder': 'respiraciones por minuto', 'min': 0}),
            'deshidratacion': forms.NumberInput(attrs={'placeholder': '%', 'min': 0, 'max': 100}),
            'tiempo_llenado_capilar': forms.NumberInput(attrs={'placeholder': 'segundos', 'step': '0.1', 'min': 0}),
            'proxima_atencion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'motivo_consulta': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Motivo de la consulta'}),
            'diagnostico': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Diagnóstico'}),
            'tratamiento': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Tratamiento indicado'}),
            'vacunas': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Vacunas aplicadas (opcional)'}),
            'alergias': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Alergias conocidas (opcional)'}),
            'cirugias_previas': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Cirugías previas (opcional)'}),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Otras observaciones (opcional)'}),
        }
        labels = {
            'peso': 'Peso (kg)',
            'temperatura': 'Temperatura (T°)',
            'frecuencia_cardiaca': 'Frecuencia cardíaca (FC)',
            'frecuencia_respiratoria': 'Frecuencia respiratoria (FR)',
            'deshidratacion': 'Deshidratación (DHT %)',
            'tiempo_llenado_capilar': 'Tiempo de llenado capilar (TLC)',
            'motivo_consulta': 'Motivo de la consulta',
            'diagnostico': 'Diagnóstico',
            'cirugias_previas': 'Cirugías previas',
            'proxima_atencion': 'Fecha de próxima atención (opcional)',
        }

    def clean_peso(self):
        peso = self.cleaned_data['peso']
        if peso <= 0:
            raise forms.ValidationError('El peso debe ser mayor a 0.')
        return peso

    def clean_proxima_atencion(self):
        fecha = self.cleaned_data.get('proxima_atencion')
        if fecha and 'proxima_atencion' in self.changed_data and fecha <= timezone.localdate():
            raise forms.ValidationError('La próxima atención debe ser una fecha futura.')
        return fecha


class BloqueoHorarioForm(forms.ModelForm):
    fecha = forms.DateField(
        label='Fecha',
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        error_messages={'required': 'Elige una fecha.'},
    )
    hora_inicio = forms.ChoiceField(
        label='Desde',
        choices=HORAS_ATENCION,
        error_messages={'required': 'Elige la hora de inicio.'},
    )
    hora_fin = forms.ChoiceField(
        label='Hasta',
        choices=HORAS_ATENCION,
        error_messages={'required': 'Elige la hora de termino.'},
    )

    class Meta:
        model = BloqueoHorario
        fields = ['fecha', 'hora_inicio', 'hora_fin', 'motivo']
        widgets = {
            'motivo': forms.TextInput(attrs={'placeholder': 'Motivo (opcional)'}),
        }

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        hoy = timezone.localdate()

        if fecha < hoy:
            raise forms.ValidationError('No puedes bloquear una fecha pasada.')

        return fecha

    def clean(self):
        cleaned_data = super().clean()
        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fin = cleaned_data.get('hora_fin')

        if hora_inicio and hora_fin:
            if hora_fin <= hora_inicio:
                self.add_error('hora_fin', 'La hora de termino debe ser despues de la hora de inicio.')

        return cleaned_data


class TipoConsultaForm(forms.ModelForm):
    class Meta:
        model = TipoConsulta
        fields = ['nombre', 'precio_base']

    def clean_precio_base(self):
        precio = self.cleaned_data.get('precio_base')
        if precio is not None and precio <= 0:
            raise forms.ValidationError('El precio debe ser mayor a 0.')
        return precio