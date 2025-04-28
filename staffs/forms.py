from django import forms
from .models import Document, User, Organization
from django.contrib.auth.forms import UserCreationForm


class SendDocumentForm(forms.ModelForm):
    recipient = forms.ModelChoiceField(queryset=User.objects.all(), required=False)
    recipient_name = forms.CharField(max_length=50, required=False, help_text="For external recipients not in the system.")

    class Meta:
        model = Document
        fields = ['document_name', 'document_description', 'summary', 'document_content', 'recipient', 'recipient_name']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)  # Получаем текущего пользователя
        super().__init__(*args, **kwargs)
        if self.user and self.user.organization and not self.user.organization.is_prime_tech:
            # Внешние организации могут отправлять только "Праймтек"
            prime_tech = Organization.objects.filter(is_prime_tech=True).first()
            if prime_tech:
                self.fields['recipient'].queryset = User.objects.filter(organization=prime_tech)

    def clean(self):
        cleaned_data = super().clean()
        recipient = cleaned_data.get('recipient')
        recipient_name = cleaned_data.get('recipient_name')

        if not recipient and not recipient_name:
            raise forms.ValidationError("Either recipient or recipient name must be provided.")
        if recipient and recipient_name:
            raise forms.ValidationError("Provide either a recipient or a recipient name, not both.")
        return cleaned_data


class CustomUserCreationForm(UserCreationForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        required=True,
        label="Organization",
        widget=forms.Select(attrs={'class': 'form-select mt-1 block w-full'})
    )
    role = forms.ChoiceField(
        choices=User.ROLES,
        required=True,
        label="Role",
        widget=forms.Select(attrs={'class': 'form-select mt-1 block w-full'})
    )

    class Meta:
        model = User
        fields = ('username', 'password1', 'password2', 'organization', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input mt-1 block w-full'})


class OrganizationCreationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'is_prime_tech']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input mt-1 block w-full'}),
            'is_prime_tech': forms.CheckboxInput(attrs={'class': 'mt-1'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if Organization.objects.filter(name=name).exists():
            raise forms.ValidationError("An organization with this name already exists.")
        return name


class OrganizationEditForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'is_prime_tech']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input mt-1 block w-full'}),
            'is_prime_tech': forms.CheckboxInput(attrs={'class': 'mt-1'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        organization_id = self.instance.id
        if Organization.objects.filter(name=name).exclude(id=organization_id).exists():
            raise forms.ValidationError("An organization with this name already exists.")
        return name