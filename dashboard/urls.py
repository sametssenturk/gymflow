from django.urls import path

from dashboard.views import DashboardStatsView, DashboardView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="index"),
    path("stats/", DashboardStatsView.as_view(), name="stats"),
]
