import json
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import AdminLibraryItem, AdminTraining, AdminTrainingExercise, CommunityReaction, TrainingRate, TrainingResult, UserExerciseRepProfile, UserProfile


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
        self.today_iso = timezone.localdate().isoformat()

    def test_save_training_results_supports_weight_result_type(self):
        response = self.client.post(
            reverse('auth:calendar_save_results'),
            data={
                'date': self.today_iso,
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
            training_date=self.today_iso,
            section=TrainingResult.SECTION_STRENGTH,
        )
        self.assertEqual(saved.result_type, TrainingResult.RESULT_WEIGHT)
        self.assertEqual(saved.minutes, 85)
        self.assertIsNone(saved.seconds)

    def test_save_training_results_supports_reps_result_type(self):
        response = self.client.post(
            reverse('auth:calendar_save_results'),
            data={
                'date': self.today_iso,
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
            training_date=self.today_iso,
            section=TrainingResult.SECTION_CARDIO,
        )
        self.assertEqual(saved.result_type, TrainingResult.RESULT_REPS)
        self.assertEqual(saved.minutes, 7)
        self.assertEqual(saved.seconds, 12)
        self.assertEqual(saved.mode, TrainingResult.MODE_SCALED)

    def test_save_training_results_for_user_denies_non_today_date(self):
        previous_day = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse('auth:calendar_save_results'),
            data={
                'date': previous_day,
                'results': {
                    'strength': {
                        'minutes': 10,
                        'seconds': 0,
                        'mode': TrainingResult.MODE_RX,
                        'result_type': TrainingResult.RESULT_TIME,
                    }
                },
            },
            content_type='application/json',
            headers={'Authorization': f'Bearer {self.access}'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get('error'), 'only_today_allowed')
        self.assertFalse(
            TrainingResult.objects.filter(
                user=self.user,
                training_date=previous_day,
                section=TrainingResult.SECTION_STRENGTH,
            ).exists()
        )


class AchievementExerciseRepProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='exercise-user@example.com',
            email='exercise-user@example.com',
            password='StrongPass123!',
        )
        self.library_item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BARBELL,
            name_ru='Front Squat',
            name_en='Front Squat',
        )

    def test_unique_profile_per_user_and_exercise_slug(self):
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug='back-pause-squat',
            rep_1=10,
            rep_2=15,
            rep_3=30,
            rep_4=40,
        )
        with self.assertRaises(IntegrityError):
            UserExerciseRepProfile.objects.create(
                user=self.user,
                exercise_slug='back-pause-squat',
                rep_1=11,
                rep_2=16,
                rep_3=31,
                rep_4=41,
            )

    def test_update_endpoint_creates_and_updates_profile(self):
        self.client.force_login(self.user)
        url = reverse('auth:achievement_exercise_update', kwargs={'exercise_slug': 'back-pause-squat'})

        first = self.client.post(
            url,
            data={'rep_1': 10, 'rep_2': 15, 'rep_3': 30, 'rep_4': 40},
            content_type='application/json',
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json().get('ok'))
        self.assertEqual(UserExerciseRepProfile.objects.filter(user=self.user, exercise_slug='back-pause-squat').count(), 1)
        self.assertEqual(first.json()['relative_percents']['p1'], 100)
        self.assertEqual(first.json()['relative_percents']['p2'], 150)
        self.assertEqual(first.json()['relative_percents']['p3'], 300)
        self.assertEqual(first.json()['relative_percents']['p4'], 400)

        second = self.client.post(
            url,
            data={'rep_1': 12, 'rep_2': 18, 'rep_3': 24, 'rep_4': 30},
            content_type='application/json',
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json().get('ok'))
        self.assertEqual(UserExerciseRepProfile.objects.filter(user=self.user, exercise_slug='back-pause-squat').count(), 1)
        profile = UserExerciseRepProfile.objects.get(user=self.user, exercise_slug='back-pause-squat')
        self.assertEqual([profile.rep_1, profile.rep_2, profile.rep_3, profile.rep_4], [12, 18, 24, 30])

    def test_update_endpoint_rejects_invalid_values(self):
        self.client.force_login(self.user)
        url = reverse('auth:achievement_exercise_update', kwargs={'exercise_slug': 'back-pause-squat'})
        response = self.client.post(
            url,
            data={'rep_1': 0, 'rep_2': 15, 'rep_3': 'abc', 'rep_4': 40},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get('error'), 'invalid_reps')

    def test_exercise_view_uses_saved_reps_and_recalculated_rows(self):
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug='back-pause-squat',
            rep_1=10,
            rep_2=15,
            rep_3=30,
            rep_4=40,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:achievement_exercise', kwargs={'exercise_slug': 'back-pause-squat'}))
        self.assertEqual(response.status_code, 200)
        exercise = response.context['exercise']
        self.assertEqual(exercise['max'], [10, 15, 30, 40])
        self.assertEqual(exercise['percent_rows'][0], [('11', '105%'), ('10', '100%'), ('10', '95%'), ('9', '90%')])
        self.assertEqual(exercise['percent_rows'][3], [('5', '45%'), ('4', '40%'), ('4', '35%'), ('3', '30%')])

    def test_library_item_view_uses_saved_reps_from_db(self):
        slug = f'library-item-{self.library_item.id}'
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug=slug,
            rep_1=33,
            rep_2=22,
            rep_3=11,
            rep_4=9,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:achievement_exercise', kwargs={'exercise_slug': slug}))
        self.assertEqual(response.status_code, 200)
        exercise = response.context['exercise']
        self.assertEqual(exercise['max'], [33, 22, 11, 9])

    def test_library_items_keep_separate_reps_for_each_slug(self):
        second_item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BARBELL,
            name_ru='Deadlift',
            name_en='Deadlift',
        )
        first_slug = f'library-item-{self.library_item.id}'
        second_slug = f'library-item-{second_item.id}'
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug=first_slug,
            rep_1=70,
            rep_2=65,
            rep_3=60,
            rep_4=55,
        )
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug=second_slug,
            rep_1=120,
            rep_2=110,
            rep_3=100,
            rep_4=90,
        )
        self.client.force_login(self.user)

        response_first = self.client.get(reverse('auth:achievement_exercise', kwargs={'exercise_slug': first_slug}))
        response_second = self.client.get(reverse('auth:achievement_exercise', kwargs={'exercise_slug': second_slug}))

        self.assertEqual(response_first.status_code, 200)
        self.assertEqual(response_second.status_code, 200)
        self.assertEqual(response_first.context['exercise']['max'], [70, 65, 60, 55])
        self.assertEqual(response_second.context['exercise']['max'], [120, 110, 100, 90])


class AchievementsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='achievements-user@example.com',
            email='achievements-user@example.com',
            password='StrongPass123!',
        )

    def test_achievements_uses_saved_first_rep_for_library_item(self):
        item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BARBELL,
            name_ru='Back Squat',
        )
        UserExerciseRepProfile.objects.create(
            user=self.user,
            exercise_slug=f'library-item-{item.id}',
            rep_1=123,
            rep_2=110,
            rep_3=100,
            rep_4=90,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:achievements'))
        self.assertEqual(response.status_code, 200)

        rows = response.context['barbell_exercises']
        row = next(entry for entry in rows if entry['slug'] == f'library-item-{item.id}')
        self.assertEqual(row['value'], 123)


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

    def test_reviews_page_filters_by_selected_period(self):
        today = timezone.localdate()
        TrainingRate.objects.create(
            user=self.user_a,
            training_date=today,
            overall=5,
            strength=5,
            cardio=5,
            metabolic=5,
            comment='Today',
        )
        TrainingRate.objects.create(
            user=self.user_b,
            training_date=today - timedelta(days=10),
            overall=3,
            strength=3,
            cardio=3,
            metabolic=3,
            comment='Old',
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse('auth:reviews_overview'), {'period': 'week'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_period'], 'week')
        cards = response.context['review_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['author_name'], 'Р’РёРєР° РџРµС‚СЂРѕРІР°')

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
        self.assertEqual(self._extract_count(activity['year']['visits']), 0)
        self.assertEqual(self._extract_count(activity['week']['goal']), 6)
        self.assertEqual(self._extract_count(activity['month']['goal']), 24)
        self.assertEqual(self._extract_count(activity['year']['goal']), 312)

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
        self.assertEqual(self._extract_count(activity['year']['visits']), 3)
        self.assertEqual(self._extract_count(activity['week']['goal']), 6)
        self.assertEqual(self._extract_count(activity['month']['goal']), 24)
        self.assertEqual(self._extract_count(activity['year']['goal']), 312)


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
        self.target_two = User.objects.create_user(
            username='target-two@example.com',
            email='target-two@example.com',
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

    def test_second_reaction_to_same_user_is_not_counted_twice(self):
        TrainingResult.objects.create(
            user=self.target,
            training_date=self.today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=9,
            seconds=10,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.sender)

        first = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target.id},
            content_type='application/json',
        )
        second = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target.id},
            content_type='application/json',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get('already_reacted'), True)
        self.assertEqual(
            CommunityReaction.objects.filter(
                sender=self.sender,
                target_user=self.target,
                training_date=self.today,
            ).count(),
            1,
        )

    def test_user_can_react_to_multiple_users_without_limit(self):
        TrainingResult.objects.create(
            user=self.target,
            training_date=self.today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=9,
            seconds=10,
            mode=TrainingResult.MODE_RX,
        )
        TrainingResult.objects.create(
            user=self.target_two,
            training_date=self.today,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=8,
            seconds=30,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.sender)

        first = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target.id},
            content_type='application/json',
        )
        second = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target_two.id},
            content_type='application/json',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            CommunityReaction.objects.filter(
                sender=self.sender,
                training_date=self.today,
            ).count(),
            2,
        )

    def test_user_can_react_to_other_user_for_selected_date(self):
        other_day = self.today - timedelta(days=1)
        TrainingResult.objects.create(
            user=self.target,
            training_date=other_day,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=8,
            seconds=5,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.sender)

        response = self.client.post(
            reverse('auth:community_react'),
            data={'target_user_id': self.target.id, 'date': other_day.isoformat()},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('ok'), True)
        self.assertTrue(
            CommunityReaction.objects.filter(
                sender=self.sender,
                target_user=self.target,
                training_date=other_day,
            ).exists()
        )


class CommunityViewDateFilterTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username='community-viewer@example.com',
            email='community-viewer@example.com',
            password='StrongPass123!',
        )
        self.target = User.objects.create_user(
            username='community-target@example.com',
            email='community-target@example.com',
            password='StrongPass123!',
        )
        self.today = timezone.localdate()

    def test_community_uses_selected_date_from_query(self):
        other_day = self.today - timedelta(days=1)
        TrainingResult.objects.create(
            user=self.target,
            training_date=other_day,
            section=TrainingResult.SECTION_STRENGTH,
            minutes=12,
            seconds=34,
            mode=TrainingResult.MODE_RX,
        )
        self.client.force_login(self.viewer)

        response = self.client.get(reverse('auth:community'), {'date': other_day.isoformat()})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['community_selected_date_iso'], other_day.isoformat())
        self.assertEqual(response.context['community_date'], other_day.strftime('%d.%m.%Y'))
        cards = response.context['community_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['target_user_id'], self.target.id)


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
        self.library_exercise = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_SQUAT,
            name_ru='Присед',
            name_en='Squat',
        )
        self.library_benchmark = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BENCHMARKS,
            benchmark_category=AdminLibraryItem.CATEGORY_GIRLS,
            name_ru='Fran',
            name_en='Fran',
        )

    def _payload(self):
        return {
            'date': '2026-04-10',
            'direction': 'crossfit',
            'visibility': 'all',
            'comment_for_coaches': 'Комментарий для тренеров',
            'comment_for_athletes': 'Комментарий для атлетов',
            'color': 'green',
            'source_type': 'library',
            'manual_description_ru': '',
            'manual_description_en': '',
            'manual_sets': '',
            'manual_result_type': '',
            'ready_workout_type': '',
            'ready_complex_type': '',
            'ready_complex_name': '',
            'ready_plan_title': '',
            'exercises': [
                {
                    'library_item_id': self.library_exercise.id,
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
        self.assertEqual(training.exercises.first().library_item_id, self.library_exercise.id)
        self.assertEqual(data['training']['exercises'][0]['library_item_id'], self.library_exercise.id)

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
        payload['comment_for_coaches'] = 'updated coaches'
        payload['comment_for_athletes'] = 'updated athletes'
        payload['color'] = 'violet'
        payload['exercises'][0]['exercise_name'] = 'РЎС‚Р°РЅРѕРІР°СЏ С‚СЏРіР°'
        update_response = self.client.post(
            reverse('auth:calendar_admin_training_update', kwargs={'training_id': training.id}),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        training.refresh_from_db()
        self.assertEqual(training.comment, '')
        self.assertEqual(training.comment_for_coaches, 'updated coaches')
        self.assertEqual(training.comment_for_athletes, 'updated athletes')
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
                'comment_for_coaches': 'Несколько упражнений',
                'comment_for_athletes': 'Комментарий для атлетов',
                'color': 'pink',
                'exercises': [
                    {
                        'library_item_id': self.library_exercise.id,
                        'block_type': 'strength',
                        'block_custom_name': '',
                        'exercise_name': 'Присед',
                        'sets': 4,
                        'reps': 8,
                        'result_type': 'reps',
                    },
                    {
                        'library_item_id': self.library_exercise.id,
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
        self.assertEqual(training.comment, '')
        self.assertEqual(training.comment_for_coaches, 'Несколько упражнений')
        self.assertEqual(training.comment_for_athletes, 'Комментарий для атлетов')
        self.assertEqual(training.color, 'pink')

        exercises = list(training.exercises.order_by('order').values('exercise_name', 'block_type', 'block_custom_name', 'result_type', 'sets', 'reps'))
        self.assertEqual(len(exercises), 2)
        self.assertEqual(exercises[0]['exercise_name'], 'Присед')
        self.assertEqual(exercises[0]['block_type'], 'strength')
        self.assertEqual(exercises[1]['exercise_name'], 'Бёрпи')
        self.assertEqual(exercises[1]['block_type'], 'custom')
        self.assertEqual(exercises[1]['block_custom_name'], 'Интервальная')

    def test_manual_training_uses_direction_as_title(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload.update(
            {
                'direction': 'gymnastics',
                'source_type': 'manual',
                'ready_plan_title': 'Тренировка с Ксенией',
                'ready_workout_type': 'ready',
                'ready_complex_type': 'benchmarks',
                'ready_complex_name': 'Test',
                'manual_description_ru': 'Описание RU',
                'manual_description_en': 'Description EN',
                'manual_sets': 3,
                'manual_result_type': 'time',
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
        self.assertEqual(data['training']['title'], 'Гимнастика')
        self.assertEqual(data['training']['ready_plan_title'], '')
        self.assertEqual(data['training']['manual_description_ru'], 'Описание RU')
        self.assertEqual(data['training']['manual_description_en'], 'Description EN')
        self.assertEqual(data['training']['manual_sets'], 3)
        self.assertEqual(data['training']['manual_result_type'], 'time')

        training = AdminTraining.objects.get(id=data['training_id'])
        self.assertEqual(training.source_type, 'manual')
        self.assertEqual(training.ready_plan_title, '')
        self.assertEqual(training.ready_workout_type, '')
        self.assertEqual(training.ready_complex_type, '')
        self.assertEqual(training.ready_complex_name, '')

    def test_manual_training_requires_manual_fields(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['source_type'] = 'manual'
        payload['exercises'] = []
        payload['manual_description_ru'] = ''
        payload['manual_description_en'] = ''
        payload['manual_sets'] = ''
        payload['manual_result_type'] = ''

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertIn('manual_description_ru', data.get('field_errors', {}))
        self.assertIn('manual_description_en', data.get('field_errors', {}))
        self.assertIn('manual_sets', data.get('field_errors', {}))
        self.assertIn('manual_result_type', data.get('field_errors', {}))

    def test_library_training_requires_sets_and_reps_for_exercise(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['exercises'][0]['sets'] = ''

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertIn('exercises.0.sets_reps', data.get('field_errors', {}))

    def test_library_training_requires_library_item_id(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['exercises'][0]['library_item_id'] = ''

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertIn('exercises.0.library_item_id', data.get('field_errors', {}))

    def test_library_training_rejects_invalid_library_item_id(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['exercises'][0]['library_item_id'] = 999999

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertEqual(
            data.get('field_errors', {}).get('exercises.0.library_item_id'),
            'invalid_library_item_id',
        )

    def test_library_training_rejects_kind_section_mismatch(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload['exercises'][0]['exercise_kind'] = 'exercise'
        payload['exercises'][0]['library_item_id'] = self.library_benchmark.id

        response = self.client.post(
            reverse('auth:calendar_admin_training_create'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertEqual(
            data.get('field_errors', {}).get('exercises.0.library_item_id'),
            'library_item_kind_mismatch',
        )


class AdminLibraryListTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-library-list@example.com',
            email='admin-library-list@example.com',
            password='AdminPass123!',
            is_staff=True,
        )

    def test_library_list_filters_by_movement_group_for_exercises(self):
        squat = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_SQUAT,
            name_ru='Back Squat',
            name_en='Back Squat',
        )
        AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_PUSH,
            name_ru='Push Up',
            name_en='Push Up',
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('auth:admin_library_list'),
            {'section': 'exercises', 'movement_group': 'squat'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        rows = data.get('rows') or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], squat.id)
        self.assertEqual(rows[0]['movement_group'], 'squat')

    def test_library_list_keeps_benchmark_category_filter(self):
        girls = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BENCHMARKS,
            benchmark_category=AdminLibraryItem.CATEGORY_GIRLS,
            name_ru='Fran',
            name_en='Fran',
        )
        AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_BENCHMARKS,
            benchmark_category=AdminLibraryItem.CATEGORY_HEROES,
            name_ru='Murph',
            name_en='Murph',
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('auth:admin_library_list'),
            {'section': 'benchmarks', 'category': 'girls'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        rows = data.get('rows') or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], girls.id)

    def test_library_list_rejects_non_admin_sections(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('auth:admin_library_list'),
            {'section': AdminLibraryItem.SECTION_BARBELL},
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('ok'))
        self.assertEqual(data.get('error'), 'invalid_section')

    def test_library_create_rejects_non_admin_sections(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('auth:admin_library_create'),
            {
                'section': AdminLibraryItem.SECTION_BARBELL,
                'name_ru': 'Strict Press',
                'name_en': 'Strict Press',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertEqual(data.get('field_errors', {}).get('section'), 'invalid_section')

    def test_library_update_rejects_non_admin_sections(self):
        item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_PUSH,
            name_ru='Push Press',
            name_en='Push Press',
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('auth:admin_library_update', args=[item.id]),
            {
                'section': AdminLibraryItem.SECTION_BARBELL,
                'name_ru': item.name_ru,
                'name_en': item.name_en,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('error'), 'validation_error')
        self.assertEqual(data.get('field_errors', {}).get('section'), 'invalid_section')
        item.refresh_from_db()
        self.assertEqual(item.section, AdminLibraryItem.SECTION_EXERCISES)


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
        self.library_with_video = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_SQUAT,
            name_ru='Присед видео',
            name_en='Video Squat',
            video_file=SimpleUploadedFile('squat.mp4', b'video-data', content_type='video/mp4'),
        )
        self.library_without_video = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_PUSH,
            name_ru='Отжимания',
            name_en='Push Up',
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

    def test_training_plan_uses_selected_date_from_query_for_admin(self):
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

        self.client.force_login(self.admin)
        response = self.client.get(reverse('auth:training_plan_today'), {'date': target_date.isoformat()})
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['comment'], 'for-target-day')
        self.assertEqual(response.context['plan_selected_date_iso'], target_date.isoformat())

    def test_training_plan_redirects_user_to_leaderboard_for_past_date(self):
        target_date = timezone.localdate() - timedelta(days=2)
        self.client.force_login(self.user)

        response = self.client.get(reverse('auth:training_plan_today'), {'date': target_date.isoformat()})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            f"{reverse('auth:leaderboard_day')}?date={target_date.isoformat()}",
        )

    def test_training_plan_allows_user_to_open_future_date(self):
        target_date = timezone.localdate() + timedelta(days=1)
        self.client.force_login(self.user)

        response = self.client.get(reverse('auth:training_plan_today'), {'date': target_date.isoformat()})

        self.assertEqual(response.status_code, 200)
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

    def test_training_plan_line_has_video_url_for_linked_library_item_with_video(self):
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='video-training',
            color='blue',
            source_type='library',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            library_item=self.library_with_video,
            exercise_kind=AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
            block_type='strength',
            exercise_name='Присед видео',
            sets=3,
            reps=8,
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        line = cards[0]['sections'][0]['lines'][0]
        self.assertTrue(line['show_video'])
        self.assertIn('library/videos/', line['video_url'])

    def test_training_plan_line_hides_video_button_without_library_video(self):
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='no-video-training',
            color='blue',
            source_type='library',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            library_item=self.library_without_video,
            exercise_kind=AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
            block_type='strength',
            exercise_name='Отжимания',
            sets=3,
            reps=12,
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        line = cards[0]['sections'][0]['lines'][0]
        self.assertFalse(line['show_video'])
        self.assertEqual(line['video_url'], '')
        self.assertEqual(line['text_ru'], 'Отжимания 3x12')
        self.assertEqual(line['text_en'], 'Отжимания 3x12')

    def test_training_plan_library_line_uses_desc_ru_en(self):
        library_item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_SQUAT,
            name_ru='Присед',
            name_en='Squat',
            desc_ru='Приседания 5 повторений по 15 раз',
            desc_en='Squat 5 sets of 15 reps',
        )
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='library-desc-training',
            color='blue',
            source_type='library',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            library_item=library_item,
            exercise_kind=AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
            block_type='strength',
            exercise_name='Присед',
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        line = response.context['plan_cards'][0]['sections'][0]['lines'][0]
        self.assertEqual(line['text_ru'], 'Приседания 5 повторений по 15 раз')
        self.assertEqual(line['text_en'], 'Squat 5 sets of 15 reps')
        self.assertEqual(line['video_search_name_ru'], 'Присед')
        self.assertEqual(line['video_search_name_en'], 'Squat')

    def test_training_plan_library_line_fallbacks_en_to_ru_desc(self):
        library_item = AdminLibraryItem.objects.create(
            section=AdminLibraryItem.SECTION_EXERCISES,
            movement_group=AdminLibraryItem.MOVEMENT_GROUP_PUSH,
            name_ru='Отжимания',
            name_en='Push Up',
            desc_ru='Отжимания 3 подхода',
            desc_en='',
        )
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='library-desc-fallback-training',
            color='blue',
            source_type='library',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            library_item=library_item,
            exercise_kind=AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
            block_type='strength',
            exercise_name='Отжимания',
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        line = response.context['plan_cards'][0]['sections'][0]['lines'][0]
        self.assertEqual(line['text_ru'], 'Отжимания 3 подхода')
        self.assertEqual(line['text_en'], 'Отжимания 3 подхода')

    def test_training_plan_manual_line_uses_manual_descriptions(self):
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='manual-desc-training',
            color='blue',
            source_type='manual',
            manual_description_ru='приседания 5 повторений по 15 раз',
            manual_description_en='squat 5 sets of 15 reps',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type='strength',
            exercise_name='ignored for manual text',
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        line = response.context['plan_cards'][0]['sections'][0]['lines'][0]
        self.assertEqual(line['text_ru'], 'приседания 5 повторений по 15 раз')
        self.assertEqual(line['text_en'], 'squat 5 sets of 15 reps')

    def test_training_plan_ready_line_uses_same_text_for_both_languages(self):
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='ready-training',
            color='blue',
            source_type='ready',
            ready_plan_title='Ready plan',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type='strength',
            exercise_name='Thruster',
            sets=4,
            reps=10,
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        line = response.context['plan_cards'][0]['sections'][0]['lines'][0]
        self.assertEqual(line['text_ru'], 'Thruster 4x10')
        self.assertEqual(line['text_en'], 'Thruster 4x10')

    def test_training_plan_version_respects_visibility(self):
        target_date = timezone.localdate()
        AdminTraining.objects.create(
            training_date=target_date,
            direction='fbb',
            visibility='all',
            comment='public',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )
        AdminTraining.objects.create(
            training_date=target_date,
            direction='crossfit',
            visibility='coaches',
            comment='private',
            color='green',
            source_type='manual',
            created_by=self.admin,
        )

        self.client.force_login(self.user)
        user_response = self.client.get(
            reverse('auth:training_plan_today_version'),
            {'date': target_date.isoformat()},
        )
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json().get('version', '').split(':')[0], '1')

        self.client.force_login(self.admin)
        admin_response = self.client.get(
            reverse('auth:training_plan_today_version'),
            {'date': target_date.isoformat()},
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json().get('version', '').split(':')[0], '2')

    def test_training_plan_version_changes_after_create(self):
        target_date = timezone.localdate()
        self.client.force_login(self.user)

        before_response = self.client.get(
            reverse('auth:training_plan_today_version'),
            {'date': target_date.isoformat()},
        )
        self.assertEqual(before_response.status_code, 200)
        before_version = before_response.json().get('version')

        AdminTraining.objects.create(
            training_date=target_date,
            direction='fbb',
            visibility='all',
            comment='new',
            color='blue',
            source_type='manual',
            created_by=self.admin,
        )

        after_response = self.client.get(
            reverse('auth:training_plan_today_version'),
            {'date': target_date.isoformat()},
        )
        self.assertEqual(after_response.status_code, 200)
        self.assertNotEqual(before_version, after_response.json().get('version'))

    def test_training_plan_line_hides_video_for_legacy_library_exercise_without_link(self):
        training = AdminTraining.objects.create(
            training_date=timezone.localdate(),
            direction='fbb',
            visibility='all',
            comment='legacy-library-training',
            color='blue',
            source_type='library',
            created_by=self.admin,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            exercise_kind=AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
            block_type='strength',
            exercise_name='Legacy Exercise',
            sets=3,
            reps=10,
            result_type='reps',
            order=0,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('auth:training_plan_today'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['plan_cards']
        line = cards[0]['sections'][0]['lines'][0]
        self.assertFalse(line['show_video'])
        self.assertEqual(line['video_url'], '')


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
        profile_a, _ = UserProfile.objects.get_or_create(user=self.user_a)
        profile_a.role = UserProfile.ROLE_ADMIN
        profile_a.save(update_fields=['role'])

    def _create_result(self, user, section, minutes, seconds, mode=TrainingResult.MODE_RX):
        return TrainingResult.objects.create(
            user=user,
            training_date=self.today,
            section=section,
            minutes=minutes,
            seconds=seconds,
            mode=mode,
        )

    def test_leaderboard_day_routes_are_available_for_user_and_admin(self):
        self.client.force_login(self.user_b)
        user_response = self.client.get(reverse('auth:leaderboard_day'))
        self.assertEqual(user_response.status_code, 200)
        self.assertTemplateUsed(user_response, 'auth/leaderboard-day.html')

        self.client.force_login(self.user_a)
        admin_user_view_response = self.client.get(reverse('auth:leaderboard_day'))
        self.assertEqual(admin_user_view_response.status_code, 200)
        self.assertTemplateUsed(admin_user_view_response, 'auth/leaderboard-day.html')

        admin_response = self.client.get(reverse('auth:leaderboard_day_admin'))
        self.assertEqual(admin_response.status_code, 200)
        self.assertTemplateUsed(admin_response, 'auth/leaderboard-day-admin.html')

    def test_leaderboard_day_admin_tv_route_is_admin_only(self):
        self.client.force_login(self.user_a)
        admin_response = self.client.get(reverse('auth:leaderboard_day_admin_tv'))
        self.assertEqual(admin_response.status_code, 200)
        self.assertTemplateUsed(admin_response, 'auth/leaderboard-day-admin-tv.html')
        self.assertEqual(admin_response.context['tv_refresh_seconds'], 30)

        self.client.force_login(self.user_b)
        user_response = self.client.get(reverse('auth:leaderboard_day_admin_tv'))
        self.assertEqual(user_response.status_code, 302)
        self.assertEqual(user_response.url, reverse('auth:profile'))

    def test_admin_can_open_user_pages(self):
        self.client.force_login(self.user_a)
        user_only_urls = [
            reverse('auth:profile'),
            reverse('auth:settings'),
            reverse('auth:support'),
            reverse('auth:support_sent'),
            reverse('auth:profile_awards_tests'),
            reverse('auth:profile_award_workout'),
            reverse('auth:community'),
            reverse('auth:training_plan_today'),
            reverse('auth:achievements'),
            reverse('auth:achievement_exercise', kwargs={'exercise_slug': 'back-pause-squat'}),
        ]

        for url in user_only_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_leaderboard_places_and_tie_break_by_updated_at(self):
        self._create_result(self.user_a, TrainingResult.SECTION_STRENGTH, 25, 10)
        self._create_result(self.user_b, TrainingResult.SECTION_STRENGTH, 26, 10)
        self._create_result(self.user_c, TrainingResult.SECTION_STRENGTH, 25, 10)
        self._create_result(self.user_d, TrainingResult.SECTION_STRENGTH, 24, 59)

        tie_older = TrainingResult.objects.get(user=self.user_a, section=TrainingResult.SECTION_STRENGTH)
        tie_newer = TrainingResult.objects.get(user=self.user_c, section=TrainingResult.SECTION_STRENGTH)
        TrainingResult.objects.filter(id=tie_older.id).update(updated_at=timezone.now() - timedelta(minutes=2))
        TrainingResult.objects.filter(id=tie_newer.id).update(updated_at=timezone.now() - timedelta(minutes=1))

        self.client.force_login(self.user_b)
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

        self.client.force_login(self.user_b)
        response = self.client.get(reverse('auth:profile'))
        self.assertEqual(response.status_code, 200)
        summary = response.context['profile_awards_summary']
        self.assertEqual(summary['first'], 2)
        self.assertEqual(summary['second'], 1)
        self.assertEqual(summary['third'], 0)

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

        self.client.force_login(self.user_b)
        response = self.client.get(reverse('auth:leaderboard_day'), {'date': other_day.isoformat()})
        self.assertEqual(response.status_code, 200)
        strength = next(item for item in response.context['leaderboard_sections'] if item['key'] == TrainingResult.SECTION_STRENGTH)
        self.assertEqual(len(strength['entries']), 1)
        self.assertEqual(strength['entries'][0]['user_id'], self.user_b.id)
        self.assertEqual(response.context['leaderboard_date'], other_day.strftime('%d.%m.%Y'))

    def test_leaderboard_builds_groups_for_all_trainings_of_day(self):
        first_training = AdminTraining.objects.create(
            training_date=self.today,
            direction='fbb',
            visibility='all',
            comment='first',
            color='blue',
            source_type='manual',
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=first_training,
            block_type='strength',
            exercise_name='Squat',
            result_type='reps',
            order=0,
        )

        second_training = AdminTraining.objects.create(
            training_date=self.today,
            direction='crossfit',
            visibility='all',
            comment='second',
            color='green',
            source_type='manual',
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=second_training,
            block_type='cardio',
            exercise_name='Run',
            result_type='time',
            order=0,
        )

        self.client.force_login(self.user_b)
        response = self.client.get(reverse('auth:leaderboard_day'), {'date': self.today.isoformat()})
        self.assertEqual(response.status_code, 200)

        groups = response.context['leaderboard_training_groups']
        self.assertEqual(len(groups), 2)
        self.assertEqual({group['title'] for group in groups}, {'FBB', 'Кроссфит с Денисом Залозним'})

    def test_admin_cards_include_direction_and_exercise_title(self):
        training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_WORKOUT,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='card',
            color=AdminTraining.COLOR_BLUE,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type=AdminTrainingExercise.BLOCK_CARDIO,
            exercise_name='Гребля',
            sets=3,
            reps=20,
            result_type=AdminTrainingExercise.RESULT_REPS,
            order=0,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:leaderboard_day_admin'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/leaderboard-day-admin.html')

        cards = response.context['leaderboard_admin_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['direction_label'], 'Тренировка дня')
        self.assertEqual(cards[0]['exercise_cards'][0]['title'], 'Гребля')

    def test_admin_cards_keep_exercise_order_by_order_and_id(self):
        training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_FBB,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='order',
            color=AdminTraining.COLOR_GREEN,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type=AdminTrainingExercise.BLOCK_STRENGTH,
            exercise_name='Второе упражнение',
            order=2,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type=AdminTrainingExercise.BLOCK_CARDIO,
            exercise_name='Первое упражнение',
            order=1,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:leaderboard_day_admin'))
        self.assertEqual(response.status_code, 200)

        cards = response.context['leaderboard_admin_cards']
        titles = [item['title'] for item in cards[0]['exercise_cards']]
        self.assertEqual(titles, ['Первое упражнение', 'Второе упражнение'])

    def test_admin_cards_allow_training_without_exercises(self):
        AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_GYMNASTICS,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='empty',
            color=AdminTraining.COLOR_ORANGE,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(reverse('auth:leaderboard_day_admin'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/leaderboard-day-admin.html')
        self.assertContains(response, 'Нет упражнений')

        cards = response.context['leaderboard_admin_cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['exercise_cards'], [])

    def test_workout_exercise_page_uses_real_training_data(self):
        training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_WORKOUT,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='detail',
            color=AdminTraining.COLOR_BLUE,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type=AdminTrainingExercise.BLOCK_CARDIO,
            exercise_name='Бег на дорожке',
            sets=3,
            reps=11,
            order=0,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse('auth:leaderboard_day_workout_exercise'),
            {'training_id': training.id, 'date': self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/leaderboard-workout-exercise-admin.html')
        self.assertContains(response, 'Бег на дорожке')
        self.assertContains(response, '3 подхода / 11 повторений')
        self.assertEqual(response.context['workout_kind_badge'], 'Кардио')

    def test_workout_exercise_page_renders_real_leader_rows(self):
        training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_WORKOUT,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='leaders',
            color=AdminTraining.COLOR_BLUE,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=training,
            block_type=AdminTrainingExercise.BLOCK_CARDIO,
            exercise_name='Бег',
            sets=3,
            reps=10,
            order=0,
        )
        TrainingResult.objects.create(
            user=self.user_b,
            training_date=self.today,
            section=TrainingResult.SECTION_CARDIO,
            minutes=12,
            seconds=10,
            mode=TrainingResult.MODE_RX,
            result_type=TrainingResult.RESULT_TIME,
        )
        TrainingResult.objects.create(
            user=self.user_c,
            training_date=self.today,
            section=TrainingResult.SECTION_CARDIO,
            minutes=11,
            seconds=20,
            mode=TrainingResult.MODE_RX,
            result_type=TrainingResult.RESULT_TIME,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse('auth:leaderboard_day_workout_exercise'),
            {'training_id': training.id, 'date': self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Таблица лидеров')
        self.assertContains(response, '12 мин 10 сек')
        self.assertTrue(response.context['workout_leader_rows'])
        self.assertEqual(len(response.context['workout_leader_rows']), 2)

    def test_workout_detail_page_uses_selected_training_data(self):
        selected_training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_GYMNASTICS,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='selected',
            color=AdminTraining.COLOR_BLUE,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=selected_training,
            block_type=AdminTrainingExercise.BLOCK_STRENGTH,
            exercise_name='Присед',
            sets=4,
            reps=8,
            order=0,
        )

        other_training = AdminTraining.objects.create(
            training_date=self.today,
            direction=AdminTraining.DIRECTION_WORKOUT,
            visibility=AdminTraining.VISIBILITY_ALL,
            comment='other',
            color=AdminTraining.COLOR_GREEN,
            source_type=AdminTraining.SOURCE_MANUAL,
            created_by=self.user_a,
        )
        AdminTrainingExercise.objects.create(
            training=other_training,
            block_type=AdminTrainingExercise.BLOCK_CARDIO,
            exercise_name='Гребля',
            sets=3,
            reps=12,
            order=0,
        )

        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse('auth:leaderboard_day_workout'),
            {'training_id': selected_training.id, 'date': self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/leaderboard-workout-detail-admin.html')
        self.assertContains(response, 'Гимнастика')
        self.assertContains(response, 'Присед')
        self.assertContains(response, '4 подхода / 8 повторений')
        self.assertNotContains(response, 'Гребля')

