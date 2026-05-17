from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from members.forms import MemberForm
from members.models import Member
from memberships.forms import MembershipForm, MembershipFreezeForm
from memberships.models import Membership


class MemberListView(AdminRequiredMixin, ListView):
    model = Member
    template_name = "members/member_list.html"
    context_object_name = "members"
    paginate_by = 25

    def get_queryset(self):
        Membership.sync_lifecycle()
        queryset = (
            Member.objects.prefetch_related("memberships__plan", "memberships__payments", "payments")
            .order_by("first_name", "last_name")
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        return queryset


class MemberDetailView(AdminRequiredMixin, DetailView):
    model = Member
    template_name = "members/member_detail.html"
    context_object_name = "member"

    def get_queryset(self):
        Membership.sync_lifecycle()
        return Member.objects.prefetch_related(
            "memberships__plan",
            "memberships__payments",
            "payments__membership__plan",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = self.object.memberships.select_related("plan").order_by(
            "-start_date",
            "-id",
        )
        context["payments"] = self.object.payments.select_related(
            "membership__plan"
        ).order_by("-payment_date", "-id")
        context["current_membership"] = self.object.active_membership or self.object.latest_membership
        return context


class MemberCreateView(SuccessMessageMixin, AdminRequiredMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = "members/member_form.html"
    success_message = "Üye başarıyla oluşturuldu."

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.object.pk})


class MemberUpdateView(SuccessMessageMixin, AdminRequiredMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = "members/member_form.html"
    success_message = "Üye bilgileri güncellendi."

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.object.pk})


class MemberDeleteView(AdminRequiredMixin, DeleteView):
    model = Member
    template_name = "members/member_confirm_delete.html"
    success_url = reverse_lazy("members:list")

    def form_valid(self, form):
        success_url = self.get_success_url()
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                "Bu üyeye bağlı üyelik veya ödeme geçmişi olduğu için silinemez.",
            )
            return redirect("members:detail", pk=self.object.pk)
        messages.success(self.request, "Üye başarıyla silindi.")
        return redirect(success_url)


class MemberMembershipCreateView(SuccessMessageMixin, AdminRequiredMixin, CreateView):
    model = Membership
    form_class = MembershipForm
    template_name = "members/membership_form.html"
    success_message = "Üyelik başarıyla oluşturuldu."

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=self.kwargs["member_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        Membership.sync_lifecycle()
        kwargs["member_id"] = self.member.pk
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member"] = self.member
        context["latest_membership"] = self.member.latest_membership
        return context

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.member.pk})


class MemberMembershipUpdateView(SuccessMessageMixin, AdminRequiredMixin, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = "members/membership_form.html"
    pk_url_kwarg = "membership_pk"
    success_message = "Üyelik güncellendi."

    def get_queryset(self):
        return Membership.objects.select_related("member", "plan").filter(
            member_id=self.kwargs["member_pk"]
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        Membership.sync_lifecycle()
        kwargs["member_id"] = self.kwargs["member_pk"]
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member"] = self.object.member
        return context

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.kwargs["member_pk"]})


class MemberMembershipDeleteView(AdminRequiredMixin, DeleteView):
    model = Membership
    template_name = "members/membership_confirm_delete.html"
    pk_url_kwarg = "membership_pk"

    def get_queryset(self):
        return Membership.objects.select_related("member", "plan").filter(
            member_id=self.kwargs["member_pk"]
        )

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.kwargs["member_pk"]})

    def form_valid(self, form):
        success_url = self.get_success_url()
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                "Bu üyelikte aktif ya da iptal edilmiş ödeme geçmişi olduğu için silinemez.",
            )
            return redirect("members:detail", pk=self.kwargs["member_pk"])
        messages.success(self.request, "Üyelik silindi.")
        return redirect(success_url)


class MemberMembershipFreezeView(AdminRequiredMixin, FormView):
    form_class = MembershipFreezeForm
    template_name = "members/membership_freeze.html"

    def dispatch(self, request, *args, **kwargs):
        Membership.sync_lifecycle()
        self.member = get_object_or_404(Member, pk=self.kwargs["member_pk"])
        self.membership = get_object_or_404(
            Membership.objects.select_related("member", "plan"),
            pk=self.kwargs["membership_pk"],
            member_id=self.member.pk,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership_start_date"] = self.membership.start_date
        kwargs["membership_end_date"] = self.membership.end_date
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member"] = self.member
        context["membership"] = self.membership
        return context

    def form_valid(self, form):
        if not self.membership.is_current:
            form.add_error(None, "Sadece aktif üyelikler dondurulabilir.")
            return self.form_invalid(form)

        freeze_start_date = form.cleaned_data["freeze_start_date"]
        freeze_end_date = form.cleaned_data["freeze_end_date"]
        freeze_days = self.membership.freeze(freeze_start_date, freeze_end_date)
        note_line = (
            f"Donduruldu: {freeze_start_date.strftime('%d.%m.%Y')} - "
            f"{freeze_end_date.strftime('%d.%m.%Y')} ({freeze_days} gün)"
        )
        if self.membership.notes:
            self.membership.notes = f"{self.membership.notes}\n{note_line}"
        else:
            self.membership.notes = note_line
        self.membership.save(
            update_fields=[
                "end_date",
                "freeze_start_date",
                "freeze_end_date",
                "status",
                "notes",
                "updated_at",
            ]
        )
        messages.success(self.request, "Üyelik donduruldu ve bitiş tarihi uzatıldı.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.member.pk})
