import json
from datetime import timedelta

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


class TrainingResultsApiTests(TestCase):
    def setUp(self):
        self.email = 'results-user@example.com'
        self.password = 'StrongPass123!'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password,
        )
        self.access = str(RefreshToken.for_user(self.user).access_token)

    def test_save_training_results_supports_weight_result_type(self):
        response = self.client.post(
            reverse('auth:calendar_save_results'),
            data={
                'date': '2026-04-13',
                'results': {
                    'strength': {
                        'minutes': 85,
                        'seconds': None,
                        'mode': TrainingResult.MODE_RX,
                        'result_type': TrainingResult.RESULT_WEIGHT,
                    }
                },
            },
            content_type='application/json',
            headers={'Authorization': f'Bearer {self.access}'},
        )
        self.assertEqual(response.status_code, 200)
        saved = TrainingResult.objects.get(
            user=self.user,
            training_date='2026-04-13',
            section=TrainingResult.SECTION_STRENGTH,
        )
        self.assertEqual(saved.result_type, TrainingResult.RESULT_WEIGHT)
        self.assertEqual(saved.minutes, 85)
        self.assertIsNone(saved.seconds)

    def test_save_training_results_supports_reps_result_type(self):
        response = self.client.post(
            reverse('auth:calendar_save_results'),
            data={
                'date': '2026-04-13',
                'results': {
                    'cardio': {
                        'minutes': 7,
                        'seconds': 12,
                        'mode': TrainingResult.MODE_SCALED,
                        'result_type': TrainingResult.RESULT_REPS,
                    }
                },
            },
            content_type='application/json',
            headers={'Authorization': f'Bearer {self.access}'},
        )
        self.assertEqual(response.status_code, 200)
        saved = TrainingResult.objects.get(
            user=self.user,
            training_date='2026-04-13',
            section=TrainingResult.SECTION_CARDIO,
        )
        self.assertEqual(saved.result_type, TrainingResult.RESULT_REPS)
        self.assertEqual(saved.minutes, 7)
        self.assertEqual(saved.seconds, 12)
        self.assertEqual(saved.mode, TrainingResult.MODE_SCALED)


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
            first_name='Р’РёРєР°',
            last_name='РџРµС‚СЂРѕРІР°',
        )
        self.user_b = User.objects.create_user(
            username='user-b@example.com',
            email='user-b@example.com',
            password='UserPass123!',
            first_name='РћР»СЏ',
            last_name='РРІР°РЅРѕРІР°',
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
            comment='РћС‚Р»РёС‡РЅР°СЏ С‚СЂРµРЅРёСЂРѕРІРєР°',
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
        self.assertEqual(cards[0]['author_name'], 'Р’РёРєР° РџРµС‚СЂРѕРІР°')
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
        self.assertEqual(cards[0]['author_name'], 'РћР»СЏ РРІР°РЅРѕРІР°')

class ProfileActivityVisitsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profile-user@example.com',
            email='profile-user@example.com',
            password='UserPass123!',
        )
        self.other_user = User.objects.create_user(
            username='profile-other@example.com',
            email='profile-other@example.com',
            password='UserPass123!',
        )

    @staticmethod
    def _extract_count(value):
        return int(str(value).split(' ', 1)[0])

    def test_profile_activity_is_zero_without_results(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 200)

        activity = json.loads(response.context['profile_activity_values_json'])
        self.assertEqual(self._extract_count(activity['week']['visits']), 0)
        self.assertEqual(self._extract_count(activity['month']['visits']), 0)
        self.assertEqual(self._extract_count(activity['all']['visits']), 0)

    def test_profile_activity_counts_unique_dates_and_is_user_scoped(self):
        today = timezone.localdate()
        within_month_date = today - timedelta(days=10)
        outside_month_date = today - timedelta(days=40)

        TrainingResult.objects.create(
            user=self.user,
            training_date=today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=10,
            seconds=20,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.user,
            training_date=today,
            section=TrainingResult.SECTION_CARDIO,
            minutes=11,
            seconds=21,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.user,
            training_date=within_month_date,
            section=TrainingResult.SECTION_METABOLIC,
            minutes=12,
            seconds=22,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.user,
            training_date=outside_month_date,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=13,
            seconds=23,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.other_user,
            training_date=today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=7,
            seconds=17,
            mode=TrainingResult.MODE_RX,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 200)

        activity = json.loads(response.context['profile_activity_values_json'])
        self.assertEqual(self._extract_count(activity['week']['visits']), 1)
        self.assertEqual(self._extract_count(activity['month']['visits']), 2)
        self.assertEqual(self._extract_count(activity['all']['visits']), 3)


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
            'comment': 'РљРѕРјРјРµРЅС‚Р°СЂРёР№ С‚СЂРµРЅРёСЂРѕРІРєРё',
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
                    'exercise_name': 'РџСЂРёСЃРµРґ',
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
            exercise_name='Р‘С‘СЂРїРё',
            result_type='time',
            order=0,
        )
        self.client.force_login(self.admin)

        payload = self._payload()
        payload['comment'] = 'updated'
        payload['color'] = 'violet'
        payload['exercises'][0]['exercise_name'] = 'РЎС‚Р°РЅРѕРІР°СЏ С‚СЏРіР°'
        update_response = self.client.post(
            reverse('auth:calendar_admin_training_update', kwargs={'training_id': training.id}),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        training.refresh_from_db()
        self.assertEqual(training.comment, 'updated')
        self.assertEqual(training.color, 'violet')
        self.assertEqual(training.exercises.first().exercise_name, 'РЎС‚Р°РЅРѕРІР°СЏ С‚СЏРіР°')

        delete_response = self.client.post(
            reverse('auth:calendar_admin_training_delete', kwargs={'training_id': training.id}),
            data={},
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(AdminTraining.objects.filter(id=training.id).exists())

    def test_admin_create_saves_multiple_exercises_and_fields(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload.update(
            {
                'date': '2026-04-12',
                'direction': 'workout',
                'visibility': 'coaches',
                'comment': 'Несколько упражнений',
                'color': 'pink',
                'exercises': [
                    {
                        'block_type': 'strength',
                        'block_custom_name': '',
                        'exercise_name': 'Присед',
                        'sets': 4,
                        'reps': 8,
                        'result_type': 'reps',
                    },
                    {
                        'block_type': 'custom',
                        'block_custom_name': 'Интервальная',
                        'exercise_name': 'Бёрпи',
                        'sets': 5,
                        'reps': 12,
                        'result_type': 'time',
                    },
                ],
            }
        )

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))

        training = AdminTraining.objects.get(id=data['training_id'])
        self.assertEqual(training.training_date.isoformat(), '2026-04-12')
        self.assertEqual(training.direction, 'workout')
        self.assertEqual(training.visibility, 'coaches')
        self.assertEqual(training.comment, 'Несколько упражнений')
        self.assertEqual(training.color, 'pink')

        exercises = list(training.exercises.order_by('order').values('exercise_name', 'block_type', 'block_custom_name', 'result_type', 'sets', 'reps'))
        self.assertEqual(len(exercises), 2)
        self.assertEqual(exercises[0]['exercise_name'], 'Присед')
        self.assertEqual(exercises[0]['block_type'], 'strength')
        self.assertEqual(exercises[1]['exercise_name'], 'Бёрпи')
        self.assertEqual(exercises[1]['block_type'], 'custom')
        self.assertEqual(exercises[1]['block_custom_name'], 'Интервальная')


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
            exercise_name='РџСЂРёСЃРµРґ',
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
            exercise_name='Р‘РµРі',
            result_type='time',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['comment'], 'public')

    def test_training_plan_uses_selected_date_from_query(self):
        target_date = timezone.localdate() - timedelta(days=2)
        another_date = timezone.localdate()

        target_training = AdminTraining.objects.create(
            training_date=target_date,
            direction='fbb',
            visibility='all',
            comment='for-target-day',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=target_training,
            block_type='strength',
            exercise_name='Присед',
            result_type='reps',
            order=0,
        )

        other_training = AdminTraining.objects.create(
            training_date=another_date,
            direction='crossfit',
            visibility='all',
            comment='for-today',
            color='green',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=other_training,
            block_type='cardio',
            exercise_name='Бег',
            result_type='time',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'), {'date': target_date.isoformat()})
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['comment'], 'for-target-day')
        self.assertEqual(response.context['plan_selected_date_iso'], target_date.isoformat())

    def test_training_plan_shows_all_trainings_for_selected_date(self):
        target_date = timezone.localdate()

        first_training = AdminTraining.objects.create(
            training_date=target_date,
            direction='fbb',
            visibility='all',
            comment='first-training',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=first_training,
            block_type='strength',
            exercise_name='Присед',
            result_type='reps',
            order=0,
        )

        second_training = AdminTraining.objects.create(
            training_date=target_date,
            direction='crossfit',
            visibility='all',
            comment='second-training',
            color='green',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=second_training,
            block_type='cardio',
            exercise_name='Бег',
            result_type='time',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'), {'date': target_date.isoformat()})
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        self.assertEqual(len(cards), 2)
        self.assertEqual({card['comment'] for card in cards}, {'first-training', 'second-training'})


class LeaderboardAwardsTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username='lb-a@example.com',
            email='lb-a@example.com',
            password='UserPass123!',
            first_name='Р’РёРєР°',
            last_name='Рђ',
        )
        self.user_b = User.objects.create_user(
            username='lb-b@example.com',
            email='lb-b@example.com',
            password='UserPass123!',
            first_name='РћР»СЏ',
            last_name='Р‘',
        )
        self.user_c = User.objects.create_user(
            username='lb-c@example.com',
            email='lb-c@example.com',
            password='UserPass123!',
            first_name='РСЂР°',
            last_name='Р’',
        )
        self.user_d = User.objects.create_user(
            username='lb-d@example.com',
            email='lb-d@example.com',
            password='UserPass123!',
            first_name='РЎРѕРЅСЏ',
            last_name='Р“',
        )
        self.today = timezone.localdate()

    def _create_result(self, user, section, minutes, seconds, mode=TrainingResult.MODE_RX):
        return TrainingResult.objects.create(
            user=user,
            training_date=self.today,
            section=section,
            minutes=minutes,
            seconds=seconds,
            mode=mode,
        )

    def test_leaderboard_places_and_tie_break_by_updated_at(self):
        self._create_result(self.user_a, TrainingResult.SECTION_STRENGTH, 25, 10)
        self._create_result(self.user_b, TrainingResult.SECTION_STRENGTH, 26, 10)
        self._create_result(self.user_c, TrainingResult.SECTION_STRENGTH, 25, 10)
        self._create_result(self.user_d, TrainingResult.SECTION_STRENGTH, 24, 59)

        tie_older = TrainingResult.objects.get(user=self.user_a, section=TrainingResult.SECTION_STRENGTH)
        tie_newer = TrainingResult.objects.get(user=self.user_c, section=TrainingResult.SECTION_STRENGTH)
        TrainingResult.objects.filter(id=tie_older.id).update(updated_at=timezone.now() - timedelta(minutes=2))
        TrainingResult.objects.filter(id=tie_newer.id).update(updated_at=timezone.now() - timedelta(minutes=1))

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:leaderboard_day'))
        self.assertEqual(response.status_code, 200)

        sections = response.context['leaderboard_sections']
        strength = next(item for item in sections if item['key'] == TrainingResult.SECTION_STRENGTH)
        self.assertEqual([row['user_id'] for row in strength['entries']], [self.user_b.id, self.user_a.id, self.user_c.id, self.user_d.id])
        self.assertEqual([row['place'] for row in strength['entries']], [1, 2, 3, 4])
        self.assertEqual([row['medal'] for row in strength['entries']], ['gold', 'silver', 'bronze', None])

    def test_profile_awards_summary_uses_today_places(self):
        self._create_result(self.user_a, TrainingResult.SECTION_STRENGTH, 28, 0)
        self._create_result(self.user_b, TrainingResult.SECTION_STRENGTH, 27, 0)
        self._create_result(self.user_c, TrainingResult.SECTION_STRENGTH, 26, 0)

        self._create_result(self.user_b, TrainingResult.SECTION_CARDIO, 31, 0)
        self._create_result(self.user_a, TrainingResult.SECTION_CARDIO, 30, 0)
        self._create_result(self.user_c, TrainingResult.SECTION_CARDIO, 29, 0)

        self._create_result(self.user_b, TrainingResult.SECTION_METABOLIC, 41, 0)
        self._create_result(self.user_c, TrainingResult.SECTION_METABOLIC, 40, 0)
        self._create_result(self.user_a, TrainingResult.SECTION_METABOLIC, 39, 0)

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 200)
        summary = response.context['profile_awards_summary']
        self.assertEqual(summary['first'], 1)
        self.assertEqual(summary['second'], 1)
        self.assertEqual(summary['third'], 1)

    def test_leaderboard_uses_selected_date_from_query(self):
        today = self.today
        other_day = today - timedelta(days=1)

        TrainingResult.objects.create(
            user=self.user_a,
            training_date=today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=10,
            seconds=0,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.user_b,
            training_date=other_day,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=20,
            seconds=0,
            mode=TrainingResult.MODE_RX,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:leaderboard_day'), {'date': other_day.isoformat()})
        self.assertEqual(response.status_code, 200)
        strength = next(item for item in response.context['leaderboard_sections'] if item['key'] == TrainingResult.SECTION_STRENGTH)
        self.assertEqual(len(strength['entries']), 1)
        self.assertEqual(strength['entries'][0]['user_id'], self.user_b.id)
        self.assertEqual(response.context['leaderboard_date'], other_day.strftime('%d.%m.%Y'))

