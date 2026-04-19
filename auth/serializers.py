from dj_rest_auth.registration.serializers import RegisterSerializer
from django.conf import settings
import hmac
import re
from rest_framework import serializers


class CustomRegisterSerializer(RegisterSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    access_key = serializers.CharField(write_only=True, min_length=8, max_length=8)

    default_error_messages = {
        'access_key_not_configured': 'Registration access key is not configured.',
        'access_key_invalid': 'Invalid access key.',
        'access_key_format': 'Access key must contain exactly 8 digits.',
    }

    def validate_access_key(self, value):
        access_key = str(value).strip()
        if not re.fullmatch(r'\d{8}', access_key):
            raise serializers.ValidationError(self.error_messages['access_key_format'])

        configured_key = str(getattr(settings, 'REGISTRATION_ACCESS_KEY', '')).strip()
        if not configured_key:
            raise serializers.ValidationError(self.error_messages['access_key_not_configured'])
        if not hmac.compare_digest(access_key, configured_key):
            raise serializers.ValidationError(self.error_messages['access_key_invalid'])
        return access_key

    def get_cleaned_data(self):
        cleaned_data = super().get_cleaned_data()
        email = self.validated_data.get('email', '')
        cleaned_data['username'] = email
        return cleaned_data
