from django.urls import path

from .views import LoginView, RegisterPasswordView, RegisterSuccessView, RegisterView

app_name = 'auth'

urlpatterns = [
    path('', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('register/password/', RegisterPasswordView.as_view(), name='register_password'),
    path('register/success/', RegisterSuccessView.as_view(), name='register_success'),
]
