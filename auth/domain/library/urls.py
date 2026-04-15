from django.urls import path

from .views import AdminLibraryCreateView, AdminLibraryListView, AdminLibraryView

urlpatterns = [
    path("admin/library/", AdminLibraryView.as_view(), name="admin_library"),
    path("admin/library/list/", AdminLibraryListView.as_view(), name="admin_library_list"),
    path("admin/library/create/", AdminLibraryCreateView.as_view(), name="admin_library_create"),
]
