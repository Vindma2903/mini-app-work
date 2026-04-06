from django.urls import path

from .views import (
    CalendarView,
    ProfileAwardWorkoutView,
    LoginView,
    ProfileAwardsTestsView,
    ProfileView,
    RegisterPasswordView,
    RegisterSuccessView,
    RegisterView,
)

app_name = 'auth'

urlpatterns = [
    path('', LoginView.as_view(), name='login'),
    path('calendar/', CalendarView.as_view(), name='calendar'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/awards-tests/', ProfileAwardsTestsView.as_view(), name='profile_awards_tests'),
    path('profile/awards-tests/workout/', ProfileAwardWorkoutView.as_view(), name='profile_award_workout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('register/password/', RegisterPasswordView.as_view(), name='register_password'),
    path('register/success/', RegisterSuccessView.as_view(), name='register_success'),
]
