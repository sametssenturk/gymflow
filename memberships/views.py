from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from members.models import Member
from memberships.forms import MembershipForm, MembershipPlanForm
from memberships.models import Membership, MembershipPlan


class SyncExpiredMembershipsMixin:
    def dispatch(self, request, *args, **kwargs):
        Membership.sync_expired()
        return super().dispatch(request, *args, **kwargs)


class MembershipPlanListView(AdminRequiredMixin, ListView):
    model = MembershipPlan
    template_name = "memberships/plan_list.html"
    context_object_name = "plans"
    paginate_by = 25

    def get_queryset(self):
        search = self.request.GET.get("q", "").strip()
        queryset = MembershipPlan.objects.order_by("-is_active", "price", "name")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset


class MembershipPlanCreateView(SuccessMessageMixin, AdminRequiredMixin, CreateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = "memberships/plan_form.html"
    success_message = "Paket başarıyla oluşturuldu."

    def get_success_url(self):
        return reverse_lazy("memberships:plan_list")


class MembershipPlanUpdateView(SuccessMessageMixin, AdminRequiredMixin, UpdateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = "memberships/plan_form.html"
    success_message = "Paket güncellendi."

    def get_success_url(self):
        return reverse_lazy("memberships:plan_list")


class MembershipPlanDeleteView(AdminRequiredMixin, DeleteView):
    model = MembershipPlan
    template_name = "memberships/plan_confirm_delete.html"
    success_url = reverse_lazy("memberships:plan_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            response = super().post(request, *args, **kwargs)
            messages.success(request, "Paket silindi.")
            return response
        except ProtectedError:
            messages.error(request, "Bu pakete bağlı üyelikler olduğu için silinemez.")
            return redirect("memberships:plan_list")


class MembershipListView(SyncExpiredMembershipsMixin, AdminRequiredMixin, ListView):
    model = Membership
    template_name = "memberships/membership_list.html"
    context_object_name = "memberships"
    paginate_by = 25

    def get_queryset(self):
        search = self.request.GET.get("q", "").strip()
        queryset = (
            Membership.objects.select_related("member", "plan")
            .order_by("-start_date", "-id")
        )
        if search:
            queryset = queryset.filter(
                Q(member__first_name__icontains=search)
                | Q(member__last_name__icontains=search)
                | Q(member__email__icontains=search)
                | Q(plan__name__icontains=search)
            )
        return queryset


class MembershipCreateView(
    SyncExpiredMembershipsMixin,
    SuccessMessageMixin,
    AdminRequiredMixin,
    CreateView,
):
    model = Membership
    form_class = MembershipForm
    template_name = "memberships/membership_form.html"
    success_message = "Üyelik başarıyla oluşturuldu."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["member_id"] = self.request.GET.get("member")
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member_id = self.request.GET.get("member")
        context["selected_member"] = (
            Member.objects.filter(pk=member_id).first() if member_id else None
        )
        return context

    def get_success_url(self):
        if self.object.member_id:
            return reverse_lazy("members:detail", kwargs={"pk": self.object.member_id})
        return reverse_lazy("memberships:membership_list")


class MembershipUpdateView(
    SyncExpiredMembershipsMixin,
    SuccessMessageMixin,
    AdminRequiredMixin,
    UpdateView,
):
    model = Membership
    form_class = MembershipForm
    template_name = "memberships/membership_form.html"
    success_message = "Üyelik güncellendi."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["member_id"] = self.request.GET.get("member") or self.object.member_id
        return kwargs

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.object.member_id})


class MembershipDeleteView(SyncExpiredMembershipsMixin, AdminRequiredMixin, DeleteView):
    model = Membership
    template_name = "memberships/membership_confirm_delete.html"
    success_url = reverse_lazy("memberships:membership_list")

    def form_valid(self, form):
        success_url = self.get_success_url()
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                "Bu üyelikte aktif ya da iptal edilmiş ödeme geçmişi olduğu için silinemez.",
            )
            return redirect("memberships:membership_list")
        messages.success(self.request, "Üyelik silindi.")
        return redirect(success_url)
