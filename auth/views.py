from django.views.generic import TemplateView


class LoginView(TemplateView):
    template_name = 'auth/login.html'


class RegisterView(TemplateView):
    template_name = 'auth/register.html'


class RegisterPasswordView(TemplateView):
    template_name = 'auth/register-password.html'


class RegisterSuccessView(TemplateView):
    template_name = 'auth/register-success.html'
