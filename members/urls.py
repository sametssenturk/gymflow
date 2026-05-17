from django.urls import path

from members.views import (
    MemberCreateView,
    MemberDeleteView,
    MemberDetailView,
    MemberListView,
    MemberMembershipCreateView,
    MemberMembershipDeleteView,
    MemberMembershipFreezeView,
    MemberMembershipUpdateView,
    MemberUpdateView,
)

app_name = "members"

urlpatterns = [
    path("", MemberListView.as_view(), name="list"),
    path("add/", MemberCreateView.as_view(), name="add"),
    path("<int:pk>/", MemberDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", MemberUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", MemberDeleteView.as_view(), name="delete"),
    path("<int:member_pk>/membership/add/", MemberMembershipCreateView.as_view(), name="membership_add"),
    path(
        "<int:member_pk>/membership/<int:membership_pk>/edit/",
        MemberMembershipUpdateView.as_view(),
        name="membership_edit",
    ),
    path(
        "<int:member_pk>/membership/<int:membership_pk>/delete/",
        MemberMembershipDeleteView.as_view(),
        name="membership_delete",
    ),
    path(
        "<int:member_pk>/membership/<int:membership_pk>/freeze/",
        MemberMembershipFreezeView.as_view(),
        name="membership_freeze",
    ),
]
