# Mini App маршруты

Ниже перечислены доступные маршруты проекта на текущий момент.

## Как запустить проект

1. Установить зависимости Python:
   - `pip install -r requirements.txt`
2. Заполнить `.env` (БД, SMTP и др. переменные).
   - Для реальной отправки писем укажи SMTP backend, например:
   - `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
3. Запустить PostgreSQL (если используешь Docker):
   - `docker compose up -d`
4. Применить миграции:
   - `python manage.py migrate`
5. Запустить сервер:
   - `python manage.py runserver`
6. Открыть приложение:
   - `http://127.0.0.1:8000/`

## Как запустить Cypress

1. Установить Node.js (проверка: `node -v` и `npm -v`).
2. В корне проекта установить Cypress:
   - `npm init -y`
   - `npm install -D cypress`
3. Первый запуск (создаст структуру папок Cypress):
   - `npx cypress open`
4. Добавить скрипты в `package.json`:
   - `cy:open` = `cypress open`
   - `cy:run` = `cypress run`
5. Убедиться, что Django-сервер запущен (`python manage.py runserver`), затем запускать:
   - `npm run cy:open` (интерактивно)
   - `npm run cy:run` (в консоли)

## Быстрый старт по экранам

- `/` — вход
- `/register/` — регистрация (шаг 1)
- `/register/password/` — регистрация (шаг 2)
- `/register/success/` — успех регистрации
- `/profile/` — профиль
- `/achievements/` — достижения
- `/calendar/` — календарь
- `/training-plan/today/` — план тренировок на сегодня
- `/community/` — комьюнити
- `/leaderboard/day/` — лидерборд дня

## Экраны mini app

- `/` — вход (`login`)
- `/register/` — регистрация, шаг 1 (`register`)
- `/register/password/` — регистрация, шаг 2 (`register_password`)
- `/register/success/` — экран успеха регистрации (`register_success`)
- `/calendar/` — календарь (`calendar`)
- `/community/` — комьюнити (`community`)
- `/training-plan/today/` — план тренировок на сегодня (`training_plan_today`)
- `/leaderboard/day/` — лидерборд дня (`leaderboard_day`)
- `/profile/` — профиль (`profile`)
- `/achievements/` — достижения (`achievements`)
- `/achievements/exercise/<slug:exercise_slug>/` — достижение по выбранному упражнению (`achievement_exercise`)
- `/profile/awards-tests/` — награды по тестам (`profile_awards_tests`)
- `/profile/awards-tests/workout/` — деталка тренировки за награду (`profile_award_workout`)

## Кастомная admin авторизация

- `/admin-auth/` — вход администратора (`admin_login`)
- `/admin-auth/password-reset/` — старт сброса пароля админа (`admin_password_reset_start`)
- `/admin-auth/password-reset/confirm/` — подтверждение кода и новый пароль (`admin_password_reset_confirm`)

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

## API документация (Swagger / ReDoc)

- `/api/schema/` — OpenAPI schema (JSON)
- `/api/schema/swagger-ui/` — Swagger UI (интерактивные запросы)
- `/api/schema/redoc/` — ReDoc
