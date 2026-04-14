from django.urls import path

from .views import CommunityView, ToggleCommunityReactionView

urlpatterns = [
    path("community/", CommunityView.as_view(), name="community"),
    path("community/react/", ToggleCommunityReactionView.as_view(), name="community_react"),
]

