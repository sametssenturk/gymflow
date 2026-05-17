from django.urls import path

from memberships.views import (
    MembershipCreateView,
    MembershipDeleteView,
    MembershipListView,
    MembershipPlanCreateView,
    MembershipPlanDeleteView,
    MembershipPlanListView,
    MembershipPlanUpdateView,
    MembershipUpdateView,
)

app_name = "memberships"

urlpatterns = [
    path("", MembershipListView.as_view(), name="membership_list"),
    path("add/", MembershipCreateView.as_view(), name="membership_add"),
    path("<int:pk>/edit/", MembershipUpdateView.as_view(), name="membership_edit"),
    path("<int:pk>/delete/", MembershipDeleteView.as_view(), name="membership_delete"),
    path("plans/", MembershipPlanListView.as_view(), name="plan_list"),
    path("plans/add/", MembershipPlanCreateView.as_view(), name="plan_add"),
    path("plans/<int:pk>/edit/", MembershipPlanUpdateView.as_view(), name="plan_edit"),
    path("plans/<int:pk>/delete/", MembershipPlanDeleteView.as_view(), name="plan_delete"),
]
