from django import forms
from django.utils import timezone
from usuarios.forms import validar_rut
from .models import Insumo, Movimiento, Proveedor


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ('nombre', 'rut', 'contacto', 'telefono', 'email', 'descripcion')
        labels = {'nombre': 'Nombre', 'rut': 'RUT', 'contacto': 'Persona de contacto', 'telefono': 'Teléfono', 'email': 'Correo', 'descripcion': 'Qué provee'}
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3, 'maxlength': 200, 'placeholder': 'Ej: vacunas, antiparasitarios y material quirúrgico'}),
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre del proveedor'}),
            'rut': forms.TextInput(attrs={'placeholder': 'RUT (ej: 76123456-7)'}),
            'contacto': forms.TextInput(attrs={'placeholder': 'Nombre de la persona de contacto'}),
            'telefono': forms.TextInput(attrs={'placeholder': '912345678', 'inputmode': 'numeric'}),
            'email': forms.EmailInput(attrs={'placeholder': 'correo@proveedor.cl'}),
        }

    def clean_rut(self):
        return validar_rut(self.cleaned_data['rut'])


class InsumoForm(forms.ModelForm):
    stock_inicial = forms.IntegerField(label='Stock inicial', min_value=0, initial=0)
    vencimiento = forms.DateField(label='Fecha de vencimiento', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta:
        model = Insumo
        fields = ('nombre', 'categoria', 'unidad', 'stock_minimo')
        labels = {'nombre': 'Nombre', 'categoria': 'Categoría', 'unidad': 'Unidad', 'stock_minimo': 'Stock mínimo'}
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej: Bravecto 20-40 kg'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if Insumo.objects.filter(nombre__iexact=nombre, activo=True).exists():
            raise forms.ValidationError('Ya existe un insumo con ese nombre.')
        return nombre

    def clean_vencimiento(self):
        vencimiento = self.cleaned_data['vencimiento']
        if vencimiento is not None and vencimiento < timezone.localdate():
            raise forms.ValidationError('La fecha de vencimiento ya pasó.')
        return vencimiento


class MovimientoForm(forms.ModelForm):
    class Meta:
        model = Movimiento
        fields = ('insumo', 'tipo', 'cantidad', 'proveedor', 'motivo')
        labels = {'insumo': 'Insumo', 'tipo': 'Tipo de movimiento', 'cantidad': 'Cantidad', 'proveedor': 'Proveedor (solo en entradas)', 'motivo': 'Motivo'}
        widgets = {
            'motivo': forms.TextInput(attrs={'placeholder': 'Ej: compra a proveedor, uso en consulta'}),
        }

    def clean_cantidad(self):
        cantidad = self.cleaned_data['cantidad']
        if cantidad == 0:
            raise forms.ValidationError('La cantidad debe ser mayor a 0.')
        return cantidad

    def clean_proveedor(self):
        proveedor = self.cleaned_data['proveedor']
        tipo = ''
        if 'tipo' in self.cleaned_data:
            tipo = self.cleaned_data['tipo']
        if proveedor is not None and tipo == 'Salida':
            raise forms.ValidationError('El proveedor solo se indica en una entrada.')
        return proveedor
