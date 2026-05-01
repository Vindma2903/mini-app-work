"""Training view exports."""

from auth.views import (
    AdminTrainingResultsView,
    AdminTrainingByDateView,
    AdminTrainingCreateView,
    AdminTrainingDeleteView,
    AdminTrainingUpdateView,
    CalendarView,
    DownloadTrainingResultsImageView,
    SaveTrainingRateView,
    SaveTrainingResultsView,
    TrainingPlanTodayView,
    TrainingPlanVersionView,
)

__all__ = [
    "AdminTrainingResultsView",
    "AdminTrainingByDateView",
    "AdminTrainingCreateView",
    "AdminTrainingDeleteView",
    "AdminTrainingUpdateView",
    "CalendarView",
    "DownloadTrainingResultsImageView",
    "SaveTrainingRateView",
    "SaveTrainingResultsView",
    "TrainingPlanTodayView",
    "TrainingPlanVersionView",
]
