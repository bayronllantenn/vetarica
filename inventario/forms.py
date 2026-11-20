from django import forms
from usuarios.forms import validar_rut
from .models import Insumo, Proveedor


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
    proveedores = forms.ModelMultipleChoiceField(queryset=Proveedor.objects.order_by('nombre'), required=False)

    class Meta:
        model = Insumo
        fields = ('nombre', 'categoria', 'stock_minimo', 'proveedores')
        labels = {'nombre': 'Nombre', 'categoria': 'Categoría', 'stock_minimo': 'Stock mínimo'}
        widgets = {'nombre': forms.TextInput(attrs={'placeholder': 'Ej: Bravecto 20-40 kg'})}

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if Insumo.objects.filter(nombre__iexact=nombre, activo=True).exists():
            raise forms.ValidationError('Ya existe un insumo con ese nombre.')
        return nombre


MOTIVOS_BAJA = [
    ('Rotura o daño', 'Rotura o daño'),
    ('Pérdida', 'Pérdida'),
    ('Uso interno de la clínica', 'Uso interno de la clínica'),
    ('Devolución al proveedor', 'Devolución al proveedor'),
    ('Corrección de inventario', 'Corrección de inventario'),
]


class BajaForm(forms.Form):
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.filter(activo=True).order_by('nombre'), label='Insumo')
    cantidad = forms.IntegerField(min_value=1, label='Cantidad')
    motivo = forms.ChoiceField(choices=MOTIVOS_BAJA, label='Motivo')


class VentaForm(forms.Form):
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.filter(activo=True, stock_actual__gt=0).order_by('nombre'), label='Producto')
    cantidad = forms.IntegerField(min_value=1, label='Cantidad')
    cliente = forms.CharField(max_length=100, label='Cliente', widget=forms.TextInput(attrs={'placeholder': 'Nombre del cliente'}))
