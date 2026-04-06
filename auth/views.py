from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .forms import LoginForm, RegisterPasswordForm, RegisterStepForm

REGISTER_SESSION_KEY = 'register_step_data'


class LoginView(FormView):
    template_name = 'auth/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('auth:login')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        login(self.request, form.user)
        return super().form_valid(form)


class RegisterView(FormView):
    template_name = 'auth/register.html'
    form_class = RegisterStepForm
    success_url = reverse_lazy('auth:register_password')

    def form_valid(self, form):
        self.request.session[REGISTER_SESSION_KEY] = {
            'first_name': form.cleaned_data['first_name'],
            'last_name': form.cleaned_data['last_name'],
            'birth_date': form.cleaned_data['birth_date'].isoformat(),
            'email': form.cleaned_data['email'],
            'phone': form.cleaned_data['phone'],
        }
        return super().form_valid(form)


class RegisterPasswordView(FormView):
    template_name = 'auth/register-password.html'
    form_class = RegisterPasswordForm
    success_url = reverse_lazy('auth:register_success')

    def dispatch(self, request, *args, **kwargs):
        if REGISTER_SESSION_KEY not in request.session:
            return redirect('auth:register')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        signup_data = self.request.session.get(REGISTER_SESSION_KEY)
        email = signup_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=form.cleaned_data['password'],
            first_name=signup_data['first_name'],
            last_name=signup_data['last_name'],
            is_active=True,
        )
        EmailAddress.objects.add_email(self.request, user, email, confirm=True)
        self.request.session.pop(REGISTER_SESSION_KEY, None)
        return super().form_valid(form)


class RegisterSuccessView(TemplateView):
    template_name = 'auth/register-success.html'

    def dispatch(self, request, *args, **kwargs):
        messages.success(
            request,
            'Мы отправили письмо на email. Подтвердите регистрацию по ссылке из письма.',
        )
        return super().dispatch(request, *args, **kwargs)


class ProfileView(TemplateView):
    template_name = 'auth/profile.html'


class ProfileAwardsTestsView(TemplateView):
    template_name = 'auth/profile-awards-tests.html'


class ProfileAwardWorkoutView(TemplateView):
    template_name = 'auth/profile-award-workout.html'


class CalendarView(TemplateView):
    template_name = 'auth/calendar.html'
