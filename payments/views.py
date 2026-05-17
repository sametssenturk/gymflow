from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from members.models import Member
from payments.forms import PaymentForm
from payments.models import Payment


class PaymentListView(AdminRequiredMixin, ListView):
    model = Payment
    template_name = "payments/payment_list.html"
    context_object_name = "payments"
    paginate_by = 25

    def get_queryset(self):
        search = self.request.GET.get("q", "").strip()
        queryset = (
            Payment.objects.select_related("member", "membership__plan")
            .order_by("-payment_date", "-id")
        )
        if search:
            queryset = queryset.filter(
                Q(member__first_name__icontains=search)
                | Q(member__last_name__icontains=search)
                | Q(member__email__icontains=search)
                | Q(membership__plan__name__icontains=search)
                | Q(note__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total = (
            self.object_list.filter(status=Payment.Status.ACTIVE).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        context["total_received"] = total
        return context


class PaymentCreateView(
    SuccessMessageMixin,
    AdminRequiredMixin,
    CreateView,
):
    model = Payment
    form_class = PaymentForm
    template_name = "payments/payment_form.html"
    success_message = "Ödeme başarıyla eklendi."

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
        return reverse_lazy("payments:list")


class PaymentUpdateView(
    SuccessMessageMixin,
    AdminRequiredMixin,
    UpdateView,
):
    model = Payment
    form_class = PaymentForm
    template_name = "payments/payment_form.html"
    success_message = "Ödeme notu güncellendi."

    def get_queryset(self):
        return Payment.objects.select_related("member", "membership__plan").filter(
            status=Payment.Status.ACTIVE
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["member_id"] = self.object.member_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_member"] = self.object.member
        return context

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.object.member_id})


class PaymentDeleteView(AdminRequiredMixin, DeleteView):
    model = Payment
    template_name = "payments/payment_confirm_delete.html"

    def get_queryset(self):
        return Payment.objects.select_related("member", "membership__plan").filter(
            status=Payment.Status.ACTIVE
        )

    def get_success_url(self):
        return reverse_lazy("members:detail", kwargs={"pk": self.object.member_id})

    def form_valid(self, form):
        success_url = self.get_success_url()
        self.object.void()
        messages.success(self.request, "Ödeme kaydı iptal edildi. Finansal geçmiş korunuyor.")
        return redirect(success_url)
