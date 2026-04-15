from .models import UserProfile


def admin_header_context(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    first_name = (user.first_name or '').strip()
    last_name = (user.last_name or '').strip()
    full_name = f'{first_name} {last_name}'.strip() or (user.email or 'Admin')
    initials = ((first_name[:1] + last_name[:1]).upper() or (user.email[:2].upper() if user.email else 'AD'))

    role = 'Admin'
    if not (user.is_staff or user.is_superuser):
        profile_role = (
            getattr(getattr(user, 'profile', None), 'role', None)
            or UserProfile.objects.filter(user=user).values_list('role', flat=True).first()
        )
        if profile_role == UserProfile.ROLE_TRAINER:
            role = 'Trainer'
        elif profile_role == UserProfile.ROLE_ADMIN:
            role = 'Admin'

    return {
        'admin_header_name': full_name,
        'admin_header_role': role,
        'admin_header_initials': initials,
    }
