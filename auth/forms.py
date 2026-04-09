from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from allauth.account.models import EmailAddress

class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    error_messages = {
        'invalid_credentials': 'Неверная почта или пароль.',
        'email_not_verified': 'Подтвердите email по ссылке из письма.',
    }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if not email or not password:
            return cleaned_data

        try:
            target_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError(self.error_messages['invalid_credentials']) from exc

        user = authenticate(self.request, username=target_user.username, password=password)
        if user is None:
            raise forms.ValidationError(self.error_messages['invalid_credentials'])

        if not EmailAddress.objects.filter(user=user, email__iexact=email, verified=True).exists():
            raise forms.ValidationError(self.error_messages['email_not_verified'])

        self.user = user
        return cleaned_data


class AdminLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    error_messages = {
        'invalid_credentials': 'Неверная почта или пароль.',
        'not_admin': 'У этой учетной записи нет доступа администратора.',
    }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if not email or not password:
            return cleaned_data

        try:
            target_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError(self.error_messages['invalid_credentials']) from exc

        user = authenticate(self.request, username=target_user.username, password=password)
        if user is None:
            raise forms.ValidationError(self.error_messages['invalid_credentials'])

        if not (user.is_staff or user.is_superuser):
            raise forms.ValidationError(self.error_messages['not_admin'])

        self.user = user
        return cleaned_data


class AdminPasswordResetStartForm(forms.Form):
    email = forms.EmailField()

    error_messages = {
        'email_not_found': 'Admin account with this email was not found.',
    }

    def __init__(self, *args, **kwargs):
        self.admin_user = None
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        if not email:
            return cleaned_data

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError(self.error_messages['email_not_found']) from exc

        if not (user.is_staff or user.is_superuser):
            raise forms.ValidationError(self.error_messages['email_not_found'])

        self.admin_user = user
        return cleaned_data


class AdminPasswordResetConfirmForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6)

    error_messages = {
        'invalid_code': 'Invalid confirmation code.',
    }

    def clean_code(self):
        return self.cleaned_data['code'].strip()


class AdminPasswordResetNewPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password_repeat = forms.CharField(widget=forms.PasswordInput, min_length=8)

    error_messages = {
        'password_mismatch': 'Passwords do not match.',
    }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_repeat = cleaned_data.get('password_repeat')

        if password and password_repeat and password != password_repeat:
            raise forms.ValidationError(self.error_messages['password_mismatch'])
        return cleaned_data


class RegisterStepForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    birth_date = forms.DateField(input_formats=['%Y-%m-%d'])
    email = forms.EmailField()
    phone = forms.CharField(max_length=32)

    error_messages = {
        'email_exists': 'Пользователь с таким email уже существует.',
    }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(self.error_messages['email_exists'])
        return email


class RegisterPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password_repeat = forms.CharField(widget=forms.PasswordInput, min_length=8)

    error_messages = {
        'password_mismatch': 'Пароли не совпадают.',
    }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_repeat = cleaned_data.get('password_repeat')
        if password and password_repeat and password != password_repeat:
            raise forms.ValidationError(self.error_messages['password_mismatch'])
        return cleaned_data
