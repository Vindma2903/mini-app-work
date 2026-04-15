"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from auth.domain.library.views import AdminLibraryView
from auth.domain.profile.views import (
    AdminProfilePasswordUpdateView,
    AdminProfileUpdateView,
    AdminProfileUserCreateView,
    AdminProfileUsersListView,
    AdminProfileView,
)

urlpatterns = [
    path('admin/profile/', AdminProfileView.as_view(), name='admin_profile_direct'),
    path('admin/profile/update/', AdminProfileUpdateView.as_view(), name='admin_profile_update_direct'),
    path('admin/profile/password/', AdminProfilePasswordUpdateView.as_view(), name='admin_profile_password_direct'),
    path('admin/profile/users/list/', AdminProfileUsersListView.as_view(), name='admin_profile_users_list_direct'),
    path('admin/profile/users/create/', AdminProfileUserCreateView.as_view(), name='admin_profile_user_create_direct'),
    path('admin/library/', AdminLibraryView.as_view(), name='admin_library_direct'),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('accounts/', include('allauth.urls')),
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('auth.api_urls')),
    path('', include('auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
