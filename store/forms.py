from django import forms
from .models import Customer

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'email', 'phone', 'address', 'credit_enabled']
        labels = {
            'name': 'Nome completo',
            'email': 'E-mail',
            'phone': 'Telefone / WhatsApp',
            'address': 'Endereço',
            'credit_enabled': 'Permitir vendas a prazo (Fiado)?',
        }
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ex: Maria Silva',
                'required': 'required'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 
                'placeholder': 'email@exemplo.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '(00) 00000-0000',
                'required': 'required'
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Rua, Número, Bairro'
            }),
            'credit_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Garante a obrigatoriedade no lado do servidor (Django)
        self.fields['name'].required = True
        self.fields['phone'].required = True
        
        # Deixa os demais campos como opcionais
        self.fields['email'].required = False
        self.fields['address'].required = False