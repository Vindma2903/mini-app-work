from django.urls import path

from .views import (
    AdminTrainingByDateView,
    AdminTrainingCreateView,
    AdminTrainingDeleteView,
    AdminTrainingResultsView,
    AdminTrainingUpdateView,
    CalendarView,
    DownloadTrainingResultsImageView,
    SaveTrainingRateView,
    SaveTrainingResultsView,
    TrainingPlanTodayView,
    TrainingPlanVersionView,
)

urlpatterns = [
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("calendar/admin-trainings/create/", AdminTrainingCreateView.as_view(), name="calendar_admin_training_create"),
    path("calendar/admin-trainings/<int:training_id>/update/", AdminTrainingUpdateView.as_view(), name="calendar_admin_training_update"),
    path("calendar/admin-trainings/<int:training_id>/delete/", AdminTrainingDeleteView.as_view(), name="calendar_admin_training_delete"),
    path("calendar/admin-trainings/<int:training_id>/results/", AdminTrainingResultsView.as_view(), name="calendar_admin_training_results"),
    path("calendar/admin-trainings/by-date/", AdminTrainingByDateView.as_view(), name="calendar_admin_training_by_date"),
    path("calendar/save-results/", SaveTrainingResultsView.as_view(), name="calendar_save_results"),
    path("calendar/save-training-rate/", SaveTrainingRateView.as_view(), name="calendar_save_training_rate"),
    path("calendar/download-results-image/", DownloadTrainingResultsImageView.as_view(), name="calendar_download_results_image"),
    path("training-plan/today/", TrainingPlanTodayView.as_view(), name="training_plan_today"),
    path("training-plan/today/version/", TrainingPlanVersionView.as_view(), name="training_plan_today_version"),
]
