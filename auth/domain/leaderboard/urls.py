from django.urls import path

from .views import (
    AchievementExerciseView,
    AchievementExerciseUpdateView,
    AchievementsView,
    LeaderboardDayView,
    LeaderboardWorkoutExerciseAdminView,
    LeaderboardWorkoutDetailAdminView,
    ProfileAwardWorkoutView,
    ProfileAwardsTestsView,
)

urlpatterns = [
    path("achievements/", AchievementsView.as_view(), name="achievements"),
    path("achievements/exercise/<slug:exercise_slug>/", AchievementExerciseView.as_view(), name="achievement_exercise"),
    path("achievements/exercise/<slug:exercise_slug>/update/", AchievementExerciseUpdateView.as_view(), name="achievement_exercise_update"),
    path("leaderboard/day/", LeaderboardDayView.as_view(), name="leaderboard_day"),
    path("leaderboard/day/workout/", LeaderboardWorkoutDetailAdminView.as_view(), name="leaderboard_day_workout"),
    path("leaderboard/day/workout/exercise/", LeaderboardWorkoutExerciseAdminView.as_view(), name="leaderboard_day_workout_exercise"),
    path("profile/awards-tests/", ProfileAwardsTestsView.as_view(), name="profile_awards_tests"),
    path("profile/awards-tests/workout/", ProfileAwardWorkoutView.as_view(), name="profile_award_workout"),
]
