import requests
from decouple import config


def leer_texto(archivo):
    respuesta = requests.post(
        'https://api.ocr.space/parse/image',
        data={'apikey': config('OCR_SPACE_KEY'), 'language': 'spa', 'OCREngine': '2', 'scale': 'true', 'isTable': 'true'},
        files={'file': (archivo.name, archivo.read())},
        timeout=30,
    )
    datos = respuesta.json()

    if datos['IsErroredOnProcessing']:
        return None

    return datos['ParsedResults'][0]['ParsedText']
