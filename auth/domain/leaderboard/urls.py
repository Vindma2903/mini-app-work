from django.urls import path

from .views import (
    AchievementExerciseView,
    AchievementExerciseUpdateView,
    AchievementsView,
    LeaderboardDayAdminView,
    LeaderboardDayAdminTvView,
    LeaderboardDayView,
    LeaderboardWorkoutExerciseAdminView,
    LeaderboardWorkoutExerciseAdminTvView,
    LeaderboardWorkoutDetailAdminView,
    LeaderboardWorkoutDetailAdminTvView,
    ProfileAwardWorkoutView,
    ProfileAwardsTestsView,
)

urlpatterns = [
    path("achievements/", AchievementsView.as_view(), name="achievements"),
    path("achievements/exercise/<slug:exercise_slug>/", AchievementExerciseView.as_view(), name="achievement_exercise"),
    path("achievements/exercise/<slug:exercise_slug>/update/", AchievementExerciseUpdateView.as_view(), name="achievement_exercise_update"),
    path("leaderboard/day/", LeaderboardDayView.as_view(), name="leaderboard_day"),
    path("leaderboard/day/admin/", LeaderboardDayAdminView.as_view(), name="leaderboard_day_admin"),
    path("leaderboard/day/admin/tv/", LeaderboardDayAdminTvView.as_view(), name="leaderboard_day_admin_tv"),
    path("leaderboard/day/workout/", LeaderboardWorkoutDetailAdminView.as_view(), name="leaderboard_day_workout"),
    path("leaderboard/day/admin/tv/workout/", LeaderboardWorkoutDetailAdminTvView.as_view(), name="leaderboard_day_workout_tv"),
    path("leaderboard/day/workout/exercise/", LeaderboardWorkoutExerciseAdminView.as_view(), name="leaderboard_day_workout_exercise"),
    path("leaderboard/day/admin/tv/workout/exercise/", LeaderboardWorkoutExerciseAdminTvView.as_view(), name="leaderboard_day_workout_exercise_tv"),
    path("profile/awards-tests/", ProfileAwardsTestsView.as_view(), name="profile_awards_tests"),
    path("profile/awards-tests/workout/", ProfileAwardWorkoutView.as_view(), name="profile_award_workout"),
]
