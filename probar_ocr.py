from inventario.ocr import leer_texto

archivo = open('orden.jpg', 'rb')
texto = leer_texto(archivo)
archivo.close()

if texto is None:
    print('No se pudo leer la imagen')
else:
    print(texto)
