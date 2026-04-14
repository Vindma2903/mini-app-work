from django.urls import path

from .views import SupportMessageSentView, SupportSubmitView, SupportView

urlpatterns = [
    path("support/", SupportView.as_view(), name="support"),
    path("support/send/", SupportSubmitView.as_view(), name="support_send"),
    path("support/sent/", SupportMessageSentView.as_view(), name="support_sent"),
]

