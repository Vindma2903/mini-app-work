from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import AdminTraining, AdminTrainingExercise, CommunityReaction, TrainingRate, TrainingResult


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
                'comment': 'Хорошая тренировка',
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
        self.assertEqual(saved.comment, 'Хорошая тренировка')


class ReviewsOverviewViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='reviews-admin@example.com',
            email='reviews-admin@example.com',
            password='AdminPass123!',
            is_staff=True,
        )
        self.user_a = User.objects.create_user(
            username='user-a@example.com',
            email='user-a@example.com',
            password='UserPass123!',
            first_name='Вика',
            last_name='Петрова',
        )
        self.user_b = User.objects.create_user(
            username='user-b@example.com',
            email='user-b@example.com',
            password='UserPass123!',
            first_name='Оля',
            last_name='Иванова',
        )

    def test_reviews_page_is_admin_only(self):
        regular = User.objects.create_user(
            username='regular@example.com',
            email='regular@example.com',
            password='UserPass123!',
        )
        self.client.force_login(regular)
        response = self.client.get(reverse('auth:reviews_overview'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auth:profile'))

    def test_reviews_page_renders_saved_training_rates(self):
        TrainingRate.objects.create(
            user=self.user_a,
            training_date='2026-04-10',
            overall=4,
            strength=4,
            cardio=5,
            metabolic=3,
            comment='Отличная тренировка',
        )
        TrainingRate.objects.create(
            user=self.user_b,
            training_date='2026-04-09',
            overall=5,
            strength=5,
            cardio=4,
            metabolic=5,
            comment='',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('auth:reviews_overview'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['review_cards']
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]['author_name'], 'Вика Петрова')
        self.assertEqual(cards[1]['comment'], 'Без комментария')

    def test_reviews_page_sorts_by_selected_rating(self):
        TrainingRate.objects.create(
            user=self.user_a,
            training_date='2026-04-10',
            overall=3,
            strength=3,
            cardio=2,
            metabolic=4,
            comment='A',
        )
        TrainingRate.objects.create(
            user=self.user_b,
            training_date='2026-04-09',
            overall=4,
            strength=4,
            cardio=5,
            metabolic=3,
            comment='B',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('auth:reviews_overview'), {'order_by': 'rating', 'load_type': 'cardio'})
        self.assertEqual(response.status_code, 200)
        cards = response.context['review_cards']
        self.assertEqual(cards[0]['author_name'], 'Оля Иванова')


class CommunityReactionApiTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            username='sender@example.com',
            email='sender@example.com',
            password='StrongPass123!',
        )
        self.target = User.objects.create_user(
            username='target@example.com',
            email='target@example.com',
            password='StrongPass123!',
        )
        self.today = timezone.localdate()

    def test_user_cannot_react_to_self(self):
        TrainingResult.objects.create(
            user=self.sender,
            training_date=self.today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=10,
            seconds=20,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.sender)

        response = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.sender.id},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get('error'), 'cannot_react_to_self')
        self.assertFalse(
            CommunityReaction.objects.filter(
                sender=self.sender,
                target_user=self.sender,
            ).exists()
        )

    def test_user_can_react_to_other_user(self):
        TrainingResult.objects.create(
            user=self.target,
            training_date=self.today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=9,
            seconds=10,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.sender)

        response = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target.id},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('ok'), True)
        self.assertTrue(
            CommunityReaction.objects.filter(
                sender=self.sender,
                target_user=self.target,
            ).exists()
        )


class AdminTrainingCrudTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-training@example.com',
            email='admin-training@example.com',
            password='AdminPass123!',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username='user-training@example.com',
            email='user-training@example.com',
            password='UserPass123!',
        )

    def _payload(self):
        return {
            'date': '2026-04-10',
            'direction': 'crossfit',
            'visibility': 'all',
            'comment': 'Комментарий тренировки',
            'color': 'green',
            'source_type': 'manual',
            'ready_workout_type': '',
            'ready_complex_type': '',
            'ready_complex_name': '',
            'ready_plan_title': '',
            'exercises': [
                {
                    'block_type': 'strength',
                    'block_custom_name': '',
                    'exercise_name': 'Присед',
                    'sets': 3,
                    'reps': 10,
                    'result_type': 'reps',
                }
            ],
        }

    def test_admin_can_create_training(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=self._payload(),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        training = AdminTraining.objects.get(id=data['training_id'])
        self.assertEqual(training.direction, 'crossfit')
        self.assertEqual(training.color, 'green')
        self.assertEqual(training.exercises.count(), 1)

    def test_regular_user_cannot_create_training(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=self._payload(),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auth:profile'))

    def test_admin_can_update_and_delete_training(self):
        training = AdminTraining.objects.create(
            training_date='2026-04-10',
            direction='fbb',
            visibility='all',
            comment='initial',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type='strength',
            exercise_name='Бёрпи',
            result_type='time',
            order=0,
        )
        self.client.force_login(self.admin)

        payload = self._payload()
        payload['comment'] = 'updated'
        payload['color'] = 'violet'
        payload['exercises'][0]['exercise_name'] = 'Становая тяга'
        update_response = self.client.post(
            reverse('auth:calendar_admin_training_update', kwargs={'training_id': training.id}),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        training.refresh_from_db()
        self.assertEqual(training.comment, 'updated')
        self.assertEqual(training.color, 'violet')
        self.assertEqual(training.exercises.first().exercise_name, 'Становая тяга')

        delete_response = self.client.post(
            reverse('auth:calendar_admin_training_delete', kwargs={'training_id': training.id}),
            data={},
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(AdminTraining.objects.filter(id=training.id).exists())


class TrainingPlanTodayVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='plan-user@example.com',
            email='plan-user@example.com',
            password='UserPass123!',
        )
        self.admin = User.objects.create_user(
            username='plan-admin@example.com',
            email='plan-admin@example.com',
            password='AdminPass123!',
            is_staff=True,
        )

    def test_training_plan_shows_only_public_trainings(self):
        public_training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='public',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=public_training,
            block_type='strength',
            exercise_name='Присед',
            result_type='reps',
            order=0,
        )

        private_training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='crossfit',
            visibility='coaches',
            comment='private',
            color='green',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=private_training,
            block_type='cardio',
            exercise_name='Бег',
            result_type='time',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['comment'], 'public')
