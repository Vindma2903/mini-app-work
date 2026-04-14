from django.urls import path

from .views import ReviewsOverviewView, StatisticsView

urlpatterns = [
    path("reviews/", ReviewsOverviewView.as_view(), name="reviews_overview"),
    path("stats/", StatisticsView.as_view(), name="statistics"),
]

