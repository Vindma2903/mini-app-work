from dj_rest_auth.registration.serializers import RegisterSerializer
from rest_framework import serializers

from .registration_access import validate_registration_access_key


class CustomRegisterSerializer(RegisterSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    access_key = serializers.CharField(write_only=True, required=True, max_length=8, min_length=8)

    def validate_access_key(self, value):
        return validate_registration_access_key(value)

    def get_cleaned_data(self):
        cleaned_data = super().get_cleaned_data()
        email = self.validated_data.get('email', '')
        cleaned_data['username'] = email
        cleaned_data['access_key'] = self.validated_data.get('access_key', '')
        return cleaned_data
