from dj_rest_auth.registration.serializers import RegisterSerializer
from rest_framework import serializers


class CustomRegisterSerializer(RegisterSerializer):
    username = serializers.CharField(required=False, allow_blank=True)

    def get_cleaned_data(self):
        cleaned_data = super().get_cleaned_data()
        email = self.validated_data.get('email', '')
        cleaned_data['username'] = email
        return cleaned_data
