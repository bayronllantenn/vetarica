from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from .forms import rango_del_dia
from .models import SolicitudCita


def enviar_recordatorios():
    manana = timezone.localdate() + timedelta(days=1)

    citas = SolicitudCita.objects.filter(
        fecha_hora__range=rango_del_dia(manana),
        estado_pago__in=['Pagado', 'En clinica'],
        recordatorio_enviado=False,
    )
    citas = citas.exclude(estado='Cancelada')

    enviados = 0
    for cita in citas:
        if not cita.email:
            continue

        hora = timezone.localtime(cita.fecha_hora).strftime('%H:%M')
        asunto = 'Recordatorio de tu cita - Vet Arica'
        mensaje = (
            f'Hola {cita.nombre}, te recordamos que mañana a las {hora} '
            f'tienes la cita de {cita.nombre_mascota} en Vet Arica. Te esperamos.'
        )
        try:
            send_mail(asunto, mensaje, None, [cita.email])
        except Exception:
            continue

        cita.recordatorio_enviado = True
        cita.save()
        enviados = enviados + 1

    return enviados