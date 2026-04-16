from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import TrainingRate
from .views import REGISTER_SESSION_KEY


class JwtAuthFlowTests(TestCase):
    def setUp(self):
        self.email = 'jwt-user@example.com'
        self.password = 'StrongPass123!'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password,
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.email,
            verified=True,
            primary=True,
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auth:login'))

    def test_login_sets_jwt_cookies_and_redirects(self):
        response = self.client.post(
            reverse('auth:login'),
            data={'email': self.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auth:profile'))
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

    def test_profile_access_with_jwt_cookies(self):
        login_response = self.client.post(
            reverse('auth:login'),
            data={'email': self.email, 'password': self.password},
        )
        self.client.cookies['access_token'] = login_response.cookies['access_token'].value
        self.client.cookies['refresh_token'] = login_response.cookies['refresh_token'].value

        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 200)

    def test_logout_blacklists_refresh_and_clears_cookies(self):
        login_response = self.client.post(
            reverse('auth:login'),
            data={'email': self.email, 'password': self.password},
        )
        refresh_value = login_response.cookies['refresh_token'].value
        self.client.cookies['refresh_token'] = refresh_value
        self.client.cookies['access_token'] = login_response.cookies['access_token'].value

        response = self.client.get(reverse('auth:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auth:login'))
        self.assertEqual(response.cookies['refresh_token'].value, '')
        self.assertEqual(response.cookies['access_token'].value, '')

        token = OutstandingToken.objects.get(token=refresh_value)
        self.assertTrue(BlacklistedToken.objects.filter(token=token).exists())


class TrainingRateApiTests(TestCase):
    def setUp(self):
        self.email = 'rate-user@example.com'
        self.password = 'StrongPass123!'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password,
        )
        self.access = str(RefreshToken.for_user(self.user).access_token)

    def test_save_training_rate_with_bearer_token(self):
        response = self.client.post(
            reverse('auth:calendar_save_training_rate'),
            data={
                'date': '2026-04-08',
                'ratings': {
                    'overall': 5,
                    'strength': 4,
                    'cardio': 5,
                    'metabolic': 3,
                },
                'comment': 'РҐРѕСЂРѕС€Р°СЏ С‚СЂРµРЅРёСЂРѕРІРєР°',
            },
            content_type='application/json',
            headers={'Authorization': f'Bearer {self.access}'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('ok'), True)

        saved = TrainingRate.objects.get(user=self.user, training_date='2026-04-08')
        self.assertEqual(saved.overall, 5)
        self.assertEqual(saved.strength, 4)
        self.assertEqual(saved.cardio, 5)
        self.assertEqual(saved.metabolic, 3)
        self.assertEqual(saved.comment, 'РҐРѕСЂРѕС€Р°СЏ С‚СЂРµРЅРёСЂРѕРІРєР°')


class RegisterFlowTests(TestCase):
    def setUp(self):
        self.email = 'existing-user@example.com'
        self.password = 'StrongPass123!'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password,
        )

    def test_register_step1_blocks_existing_email(self):
        response = self.client.post(
            reverse('auth:register'),
            data={
                'first_name': 'Ivan',
                'last_name': 'Ivanov',
                'birth_date': '2000-01-01',
                'email': self.email,
                'phone': '+79990001122',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пользователь с таким email уже существует.')
        self.assertNotIn(REGISTER_SESSION_KEY, self.client.session)

    def test_register_step2_handles_duplicate_without_server_error(self):
        session = self.client.session
        session[REGISTER_SESSION_KEY] = {
            'first_name': 'Petr',
            'last_name': 'Petrov',
            'birth_date': '1999-09-09',
            'email': self.email,
            'phone': '+79990003344',
        }
        session.save()

        response = self.client.post(
            reverse('auth:register_password'),
            data={
                'password': 'AnotherPass123!',
                'password_repeat': 'AnotherPass123!',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пользователь с таким email уже существует.')
        self.assertEqual(User.objects.filter(username=self.email).count(), 1)
