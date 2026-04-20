# Mini App

## Запуск проекта

```powershell
cd C:\Users\Public\mini-app-work
.\.venv\Scripts\Activate.ps1
docker compose up -d
python manage.py migrate
python manage.py runserver 127.0.0.1:8000 --noreload
```

## Все экраны (быстрые ссылки)

### Пользовательские экраны
- Вход: http://localhost:8000/
- Регистрация (шаг 1): http://localhost:8000/register/
- Регистрация (шаг 2): http://localhost:8000/register/password/
- Успех регистрации: http://localhost:8000/register/success/
- Профиль: http://localhost:8000/profile/
- Настройки: http://localhost:8000/settings/
- Комьюнити: http://localhost:8000/community/
- План тренировок на сегодня: http://localhost:8000/training-plan/today/
- Достижения: http://localhost:8000/achievements/
- Достижение по упражнению: http://localhost:8000/achievements/exercise/back-pause-squat/
- Лидерборд дня: http://localhost:8000/leaderboard/day/
- Награды по тестам: http://localhost:8000/profile/awards-tests/
- Детали тренировки за награду: http://localhost:8000/profile/awards-tests/workout/
- Поддержка: http://localhost:8000/support/
- Поддержка (отправлено): http://localhost:8000/support/sent/

### Админские экраны
- Админ-авторизация: http://localhost:8000/admin-auth/
- Сброс пароля админа (email): http://localhost:8000/admin-auth/password-reset/
- Подтверждение кода: http://localhost:8000/admin-auth/password-reset/confirm/
- Новый пароль: http://localhost:8000/admin-auth/password-reset/new-password/
- Админский экран тренировок (календарь): http://localhost:8000/calendar/
- Django admin: http://localhost:8000/admin/

## Что важно по тренировочным экранам

В проекте сейчас есть **два разных** экрана, связанных с тренировками:
- `http://localhost:8000/training-plan/today/` — пользовательский экран (из нижнего меню «Тренировки»).
- `http://localhost:8000/calendar/` — админский экран календаря тренировок.

## API и документация

- OpenAPI schema: http://localhost:8000/api/schema/
- Swagger UI: http://localhost:8000/api/schema/swagger-ui/
- ReDoc: http://localhost:8000/api/schema/redoc/

### API auth (dj-rest-auth + JWT)
- POST login: http://localhost:8000/api/auth/login/
- POST logout: http://localhost:8000/api/auth/logout/
- GET/PUT user: http://localhost:8000/api/auth/user/
- POST password change: http://localhost:8000/api/auth/password/change/
- POST password reset: http://localhost:8000/api/auth/password/reset/
- POST password reset confirm: http://localhost:8000/api/auth/password/reset/confirm/
- POST token refresh: http://localhost:8000/api/auth/token/refresh/
- POST token verify: http://localhost:8000/api/auth/token/verify/

### API registration
- Регистрация: http://localhost:8000/api/auth/registration/
- Подтверждение email: http://localhost:8000/api/auth/registration/verify-email/
- Повторная отправка письма: http://localhost:8000/api/auth/registration/resend-email/
- Подтверждение по ключу: http://localhost:8000/api/auth/registration/account-confirm-email/<key>/

## Пользователи по умолчанию

Создаются автоматически при старте приложения (если `AUTO_CREATE_ADMIN=1`):
- Админ: `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`
- Обычный пользователь: `DEFAULT_USER_EMAIL` / `DEFAULT_USER_PASSWORD`

Также можно создать вручную:

```powershell
python manage.py seed_admin
```

## Ключ доступа при регистрации

- Для регистрации пользователя нужен ключ из 8 цифр.
- Ключ задается переменной окружения `REGISTRATION_ACCESS_KEY` (см. `.env.example`).
