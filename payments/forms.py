from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from core.forms import BootstrapModelForm
from members.models import Member
from memberships.models import Membership
from payments.models import Payment


class PaymentForm(BootstrapModelForm):
    class Meta:
        model = Payment
        fields = ["member", "membership", "amount", "payment_date", "payment_method", "note"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, member_id=None, **kwargs):
        self.member_id = member_id
        super().__init__(*args, **kwargs)
        Membership.sync_lifecycle()
        self.fields["member"].queryset = Member.objects.order_by("first_name", "last_name")
        paid_total = Coalesce(
            Sum(
                "payments__amount",
                filter=Q(payments__status=Payment.Status.ACTIVE),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
        membership_filter = Q(agreed_price__gt=F("paid_total"))
        if self.instance and self.instance.pk and self.instance.membership_id:
            membership_filter |= Q(pk=self.instance.membership_id)
        membership_queryset = (
            Membership.objects.select_related("member", "plan")
            .prefetch_related("payments")
            .annotate(paid_total=paid_total)
            .filter(membership_filter)
            .order_by("member__first_name", "member__last_name", "-start_date", "-id")
        )
        self.fields["membership"].queryset = membership_queryset.order_by(
            "member__first_name",
            "member__last_name",
            "-start_date",
            "-id",
        )
        self.fields["membership"].label_from_instance = (
            lambda membership: membership.display_label(include_balance=True)
        )
        self.fields["membership"].help_text = "Ödeme ilgili üyeliğe bağlanır."

        if member_id:
            self.fields["member"].initial = member_id
            self.fields["member"].queryset = self.fields["member"].queryset.filter(pk=member_id)
            self.fields["membership"].queryset = self.fields["membership"].queryset.filter(
                member_id=member_id
            )
            if not self.instance.pk and self.fields["membership"].queryset.count() == 1:
                self.fields["membership"].initial = self.fields["membership"].queryset.first()

        if self.instance and self.instance.pk:
            for field_name in ["member", "membership", "amount", "payment_date", "payment_method"]:
                self.fields[field_name].disabled = True
            self.fields["note"].help_text = (
                "Finansal alanlar geçmişi korumak için kilitlidir. Gerekirse bu kaydı iptal edip yeni ödeme açın."
            )
        else:
            self.fields["amount"].help_text = "Girilen tutar, kalan borcu aşamaz."

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get("member")
        membership = cleaned_data.get("membership")

        if member and membership and membership.member_id != member.id:
            raise ValidationError({"membership": "Seçilen üyelik, seçilen üyeye ait değil."})

        return cleaned_data
