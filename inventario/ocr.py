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


def separar_productos(texto):
    productos = []

    for linea in texto.split('\n'):
        celdas = []
        for celda in linea.split('\t'):
            celda = celda.strip()
            if celda != '':
                celdas.append(celda)

        precios = []
        for celda in celdas:
            if celda.startswith('$'):
                precios.append(celda)

        if len(precios) < 2:
            continue

        for i in range(len(celdas)):
            partes = celdas[i].split(' ', 1)

            if len(partes) == 2 and partes[0].isdigit():
                cantidad = partes[0]
                nombre = partes[1]

                if i + 1 < len(celdas) and celdas[i + 1].isdigit():
                    cantidad = celdas[i + 1]

                precio = precios[0].replace('$', '').replace('.', '')

                productos.append({'cantidad': int(cantidad), 'nombre': nombre, 'precio': int(precio)})
                break

    return productos
