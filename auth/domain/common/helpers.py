"""Compatibility exports for shared helper functions."""

from auth.views import (
    build_week_days,
    get_client_ip,
    get_user_role,
    resolve_request_user,
    user_has_admin_panel_access,
)

__all__ = [
    "build_week_days",
    "get_client_ip",
    "get_user_role",
    "resolve_request_user",
    "user_has_admin_panel_access",
]

