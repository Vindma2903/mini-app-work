# Mini App маршруты

Ниже перечислены доступные маршруты проекта на текущий момент.

## Основные страницы

- `/` — вход (`login`)
- `/register/` — регистрация, шаг 1 (`register`)
- `/register/password/` — регистрация, шаг 2 (`register_password`)
- `/register/success/` — экран успеха регистрации (`register_success`)
- `/calendar/` — календарь (`calendar`)
- `/leaderboard/day/` — лидерборд дня (`leaderboard_day`)
- `/profile/` — профиль (`profile`)
- `/profile/awards-tests/` — награды по тестам (`profile_awards_tests`)
- `/profile/awards-tests/workout/` — деталка тренировки за награду (`profile_award_workout`)

## Админка

- `/admin/` — Django admin

## Allauth (web auth)

- `/accounts/login/`
- `/accounts/logout/`
- `/accounts/signup/`
- `/accounts/email/`
- `/accounts/confirm-email/`
- `/accounts/confirm-email/<key>/`
- `/accounts/password/change/`
- `/accounts/password/reset/`
- `/accounts/password/reset/done/`
- `/accounts/password/reset/key/<uidb36>-<key>/`
- `/accounts/password/reset/key/done/`
- `/accounts/password/set/`
- `/accounts/reauthenticate/`
- `/accounts/inactive/`

## API auth (dj-rest-auth + JWT)

- `/api/auth/login/` — вход
- `/api/auth/logout/` — выход
- `/api/auth/user/` — профиль пользователя
- `/api/auth/password/change/` — смена пароля
- `/api/auth/password/reset/` — сброс пароля
- `/api/auth/password/reset/confirm/` — подтверждение сброса
- `/api/auth/token/refresh/` — refresh JWT
- `/api/auth/token/verify/` — проверка JWT

## API registration

- `/api/auth/registration/` — регистрация (custom `EmailRegisterView`)
- `/api/auth/registration/verify-email/` — подтверждение email
- `/api/auth/registration/resend-email/` — повторная отправка письма
- `/api/auth/registration/account-confirm-email/<key>/` — подтверждение email по ключу
