from django.urls import path

from .views import AdminLibraryView

urlpatterns = [
    path("admin/library/", AdminLibraryView.as_view(), name="admin_library"),
]

