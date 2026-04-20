from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(REGISTRATION_ACCESS_KEY="12345678")
class RegistrationAccessKeyTests(TestCase):
    def _register_step_payload(self, **overrides):
        payload = {
            "first_name": "Ivan",
            "last_name": "Petrov",
            "birth_date": "1990-01-01",
            "email": "ivan.petrov@example.com",
            "phone": "79991234567",
            "access_key": "12345678",
        }
        payload.update(overrides)
        return payload

    def test_register_step_rejects_wrong_access_key(self):
        response = self.client.post(
            reverse("auth:register"),
            data=self._register_step_payload(access_key="87654321"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_key", response.context["form"].errors)
        self.assertNotIn("register_step_data", self.client.session)

    def test_register_step_accepts_valid_access_key(self):
        response = self.client.post(
            reverse("auth:register"),
            data=self._register_step_payload(),
        )

        self.assertRedirects(response, reverse("auth:register_password"))
        self.assertEqual(self.client.session["register_step_data"]["email"], "ivan.petrov@example.com")

    def test_api_registration_rejects_wrong_access_key(self):
        response = self.client.post(
            reverse("rest_register"),
            data={
                "email": "api.user@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "access_key": "87654321",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("access_key", response.json())
