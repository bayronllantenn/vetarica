from django import forms
from usuarios.forms import validar_rut
from .models import Insumo, Movimiento, Proveedor


class ProveedorForm(forms.ModelForm):
    insumos = forms.ModelMultipleChoiceField(
        queryset=Insumo.objects.order_by('nombre'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Insumos que entrega',
    )

    class Meta:
        model = Proveedor
        fields = ('nombre', 'rut', 'contacto', 'telefono', 'email')
        labels = {'nombre': 'Nombre','rut': 'RUT','contacto': 'Persona de contacto','telefono': 'Teléfono','email': 'Correo',}
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre del proveedor'}),
            'rut': forms.TextInput(attrs={'placeholder': 'RUT (ej: 76123456-7)'}),
            'contacto': forms.TextInput(attrs={'placeholder': 'Nombre de la persona de contacto'}),
            'telefono': forms.TextInput(attrs={'placeholder': '912345678', 'inputmode': 'numeric'}),
            'email': forms.EmailInput(attrs={'placeholder': 'correo@proveedor.cl'}),
        }

    def clean_rut(self):
        return validar_rut(self.cleaned_data['rut'])

    def save(self, commit=True):
        proveedor = super().save(commit)
        if commit:
            proveedor.insumos.set(self.cleaned_data['insumos'])
        return proveedor


class MovimientoForm(forms.ModelForm):
    class Meta:
        model = Movimiento
        fields = ('insumo', 'tipo', 'cantidad', 'motivo')
        labels = {'insumo': 'Insumo', 'tipo': 'Tipo de movimiento', 'cantidad': 'Cantidad', 'motivo': 'Motivo'}
        widgets = {
            'motivo': forms.TextInput(attrs={'placeholder': 'Ej: compra a proveedor, uso en consulta'}),
        }

    def clean_cantidad(self):
        cantidad = self.cleaned_data['cantidad']
        if cantidad == 0:
            raise forms.ValidationError('La cantidad debe ser mayor a 0.')
        return cantidad
