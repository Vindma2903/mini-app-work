from django.urls import path

from .views import AdminLibraryCreateView, AdminLibraryDeleteView, AdminLibraryListView, AdminLibraryUpdateView, AdminLibraryView

urlpatterns = [
    path("admin/library/", AdminLibraryView.as_view(), name="admin_library"),
    path("admin/library/list/", AdminLibraryListView.as_view(), name="admin_library_list"),
    path("admin/library/create/", AdminLibraryCreateView.as_view(), name="admin_library_create"),
    path("admin/library/update/<int:item_id>/", AdminLibraryUpdateView.as_view(), name="admin_library_update"),
    path("admin/library/delete/<int:item_id>/", AdminLibraryDeleteView.as_view(), name="admin_library_delete"),
]
