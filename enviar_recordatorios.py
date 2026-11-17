import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from citas.recordatorios import enviar_recordatorios

enviados = enviar_recordatorios()
print('Recordatorios enviados:', enviados)
