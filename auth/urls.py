from django.urls import path

from .views import (
    AchievementExerciseView,
    AchievementsView,
    AdminLoginView,
    AdminPasswordResetConfirmView,
    AdminPasswordResetStartView,
    CalendarView,
    CommunityView,
    LeaderboardDayView,
    ProfileAwardWorkoutView,
    LoginView,
    LogoutView,
    ProfileAwardsTestsView,
    ProfileView,
    RegisterPasswordView,
    RegisterSuccessView,
    DownloadTrainingResultsImageView,
    RegisterView,
    SaveTrainingResultsView,
    SaveTrainingRateView,
    TrainingPlanTodayView,
)

app_name = 'auth'

urlpatterns = [
    path('', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('admin-auth/', AdminLoginView.as_view(), name='admin_login'),
    path('admin-auth/password-reset/', AdminPasswordResetStartView.as_view(), name='admin_password_reset_start'),
    path('admin-auth/password-reset/confirm/', AdminPasswordResetConfirmView.as_view(), name='admin_password_reset_confirm'),
    path('calendar/', CalendarView.as_view(), name='calendar'),
    path('calendar/save-results/', SaveTrainingResultsView.as_view(), name='calendar_save_results'),
    path('calendar/save-training-rate/', SaveTrainingRateView.as_view(), name='calendar_save_training_rate'),
    path('calendar/download-results-image/', DownloadTrainingResultsImageView.as_view(), name='calendar_download_results_image'),
    path('community/', CommunityView.as_view(), name='community'),
    path('training-plan/today/', TrainingPlanTodayView.as_view(), name='training_plan_today'),
    path('achievements/', AchievementsView.as_view(), name='achievements'),
    path('achievements/exercise/<slug:exercise_slug>/', AchievementExerciseView.as_view(), name='achievement_exercise'),
    path('leaderboard/day/', LeaderboardDayView.as_view(), name='leaderboard_day'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/awards-tests/', ProfileAwardsTestsView.as_view(), name='profile_awards_tests'),
    path('profile/awards-tests/workout/', ProfileAwardWorkoutView.as_view(), name='profile_award_workout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('register/password/', RegisterPasswordView.as_view(), name='register_password'),
    path('register/success/', RegisterSuccessView.as_view(), name='register_success'),
]
