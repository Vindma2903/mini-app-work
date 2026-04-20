from dj_rest_auth.registration.views import RegisterView
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from .registration_access import validate_registration_access_key


class EmailRegisterView(RegisterView):
    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if data is not None:
            mutable_data = data.copy()
            try:
                mutable_data['access_key'] = validate_registration_access_key(
                    mutable_data.get('access_key', '')
                )
            except DjangoValidationError as exc:
                message = exc.messages[0] if exc.messages else 'Неверный ключ доступа.'
                raise ValidationError({'access_key': [message]}) from exc
            if not mutable_data.get('username') and mutable_data.get('email'):
                mutable_data['username'] = mutable_data['email']
            kwargs['data'] = mutable_data
        return super().get_serializer(*args, **kwargs)
