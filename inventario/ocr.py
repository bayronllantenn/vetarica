import requests
from decouple import config
from .models import Insumo


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


UNIDADES = ['CAJA', 'CAJAS', 'UN', 'UND', 'UNID', 'UNIDAD', 'UNIDADES', 'BOLSA', 'BOLSAS', 'FRASCO', 'FRASCOS', 'ML', 'KG']


def es_codigo(texto):
    if ' ' in texto or '-' not in texto:
        return False
    for letra in texto:
        if letra.isdigit():
            return True
    return False


def solo_numero(texto):
    return texto.replace('$', '').replace('.', '').replace(',', '').replace(' ', '')


def separar_productos(texto):
    productos = []
    anterior = ''

    for linea in texto.split('\n'):
        celdas = []
        for celda in linea.split('\t'):
            celda = celda.strip()
            if celda != '':
                celdas.append(celda)

        precios = []
        cantidad = ''
        textos = []
        for celda in celdas:
            if celda.startswith('$'):
                precios.append(solo_numero(celda))
            elif celda.isdigit():
                if cantidad == '':
                    cantidad = celda
            elif es_codigo(celda) or celda.upper() in UNIDADES:
                continue
            else:
                textos.append(celda)
        nombre = ' '.join(textos)

        partes = nombre.split(' ', 1)
        if len(partes) == 2 and es_codigo(partes[0]):
            nombre = partes[1]

        partes = nombre.split(' ', 1)
        if len(partes) == 2 and partes[0].isdigit():
            nombre = partes[1]
            if cantidad == '':
                cantidad = partes[0]

        if len(precios) < 2:
            mayusculas = nombre.upper()
            if mayusculas.startswith('LOT') or 'DESCRIP' in mayusculas or 'NETO' in mayusculas:
                anterior = ''
            else:
                anterior = nombre
            continue

        codigo_solo = es_codigo(celdas[0])
        if codigo_solo or nombre == '' or nombre.startswith('(') or nombre.upper().startswith('CAJA'):
            nombre = (anterior + ' ' + nombre).strip()
        anterior = ''

        precio = precios[0]
        total = precios[-1]
        if not precio.isdigit() or int(precio) == 0:
            continue
        if cantidad == '' and total.isdigit():
            cantidad = str(int(total) // int(precio))
        if cantidad == '' or nombre == '':
            continue

        productos.append({'cantidad': int(cantidad), 'nombre': nombre, 'precio': int(precio)})

    return productos


def buscar_insumo(nombre):
    insumos = Insumo.objects.all()

    for insumo in insumos:
        if insumo.nombre.upper() in nombre.upper():
            return insumo

    return None
