from django.urls import path

from .views import (
    AdminLoginView,
    AdminPasswordResetConfirmView,
    AdminPasswordResetStartView,
    CalendarView,
    CommunityView,
    LeaderboardDayView,
    ProfileAwardWorkoutView,
    LoginView,
    ProfileAwardsTestsView,
    ProfileView,
    RegisterPasswordView,
    RegisterSuccessView,
    RegisterView,
    TrainingPlanTodayView,
)

app_name = 'auth'

urlpatterns = [
    path('', LoginView.as_view(), name='login'),
    path('admin-auth/', AdminLoginView.as_view(), name='admin_login'),
    path('admin-auth/password-reset/', AdminPasswordResetStartView.as_view(), name='admin_password_reset_start'),
    path('admin-auth/password-reset/confirm/', AdminPasswordResetConfirmView.as_view(), name='admin_password_reset_confirm'),
    path('calendar/', CalendarView.as_view(), name='calendar'),
    path('community/', CommunityView.as_view(), name='community'),
    path('training-plan/today/', TrainingPlanTodayView.as_view(), name='training_plan_today'),
    path('leaderboard/day/', LeaderboardDayView.as_view(), name='leaderboard_day'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/awards-tests/', ProfileAwardsTestsView.as_view(), name='profile_awards_tests'),
    path('profile/awards-tests/workout/', ProfileAwardWorkoutView.as_view(), name='profile_award_workout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('register/password/', RegisterPasswordView.as_view(), name='register_password'),
    path('register/success/', RegisterSuccessView.as_view(), name='register_success'),
]
