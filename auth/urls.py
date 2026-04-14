from django.urls import include, path

app_name = 'auth'

urlpatterns = [
    path('', include('auth.domain.authn.urls')),
    path('', include('auth.domain.profile.urls')),
    path('', include('auth.domain.training.urls')),
    path('', include('auth.domain.community.urls')),
    path('', include('auth.domain.leaderboard.urls')),
    path('', include('auth.domain.support.urls')),
    path('', include('auth.domain.library.urls')),
    path('', include('auth.domain.statistics.urls')),
]
