from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.forms import BootstrapModelForm
from members.models import Member
from memberships.models import Membership, MembershipPlan


class MembershipPlanForm(BootstrapModelForm):
    class Meta:
        model = MembershipPlan
        fields = ["name", "duration_days", "price", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class MembershipForm(BootstrapModelForm):
    class Meta:
        model = Membership
        fields = ["member", "plan", "start_date", "end_date", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, member_id=None, **kwargs):
        self.member_id = member_id
        super().__init__(*args, **kwargs)
        Membership.sync_lifecycle()
        self.fields["member"].queryset = Member.objects.order_by("first_name", "last_name")
        plan_queryset = MembershipPlan.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.plan_id:
            plan_queryset = plan_queryset | MembershipPlan.objects.filter(pk=self.instance.plan_id)
        self.fields["plan"].queryset = plan_queryset.distinct().order_by(
            "price", "name"
        )
        self.fields["end_date"].required = False
        self.fields["end_date"].help_text = "Boş bırakılırsa paket süresine göre otomatik hesaplanır."
        if member_id:
            self.fields["member"].initial = member_id
            self.fields["member"].queryset = self.fields["member"].queryset.filter(pk=member_id)

    def clean(self):
        Membership.sync_lifecycle()
        cleaned_data = super().clean()
        member = cleaned_data.get("member")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        plan = cleaned_data.get("plan")

        if member:
            today = timezone.localdate()
            open_memberships = Membership.objects.filter(
                member=member,
                status__in=[
                    Membership.Status.ACTIVE,
                    Membership.Status.PAUSED,
                    Membership.Status.PLANNED,
                ],
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            if self.instance and self.instance.pk:
                open_memberships = open_memberships.exclude(pk=self.instance.pk)
            if open_memberships.exists():
                raise ValidationError(
                    {"member": "Bu üyenin aktif, planlı ya da dondurulmuş bir üyeliği var."}
                )

        if start_date and end_date and end_date < start_date:
            raise ValidationError({"end_date": "Bitiş tarihi başlangıç tarihinden önce olamaz."})

        if not end_date and start_date and plan:
            cleaned_data["end_date"] = start_date + timedelta(days=plan.duration_days)

        return cleaned_data


class MembershipFreezeForm(forms.Form):
    freeze_start_date = forms.DateField(
        label="Dondurma başlangıcı",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    freeze_end_date = forms.DateField(
        label="Dondurma bitişi",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, membership_start_date=None, membership_end_date=None, **kwargs):
        self.membership_start_date = membership_start_date
        self.membership_end_date = membership_end_date
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["freeze_start_date"].help_text = "Dondurma başlangıcını seçin."
        self.fields["freeze_end_date"].help_text = "Dondurma bitişini seçin."

    def clean(self):
        cleaned_data = super().clean()
        freeze_start_date = cleaned_data.get("freeze_start_date")
        freeze_end_date = cleaned_data.get("freeze_end_date")
        today = timezone.localdate()

        if freeze_start_date and freeze_end_date and freeze_end_date < freeze_start_date:
            raise ValidationError({"freeze_end_date": "Dondurma bitiş tarihi başlangıç tarihinden önce olamaz."})

        if freeze_start_date and freeze_start_date > today:
            raise ValidationError({"freeze_start_date": "Dondurma başlangıcı gelecekte olamaz."})

        if (
            self.membership_start_date
            and freeze_start_date
            and freeze_start_date < self.membership_start_date
        ):
            raise ValidationError(
                {"freeze_start_date": "Dondurma başlangıcı üyelik başlangıcından önce olamaz."}
            )

        if (
            self.membership_end_date
            and freeze_end_date
            and freeze_end_date > self.membership_end_date
        ):
            raise ValidationError(
                {"freeze_end_date": "Dondurma bitiş tarihi mevcut üyelik bitiş tarihini aşamaz."}
            )

        if self.membership_end_date and freeze_start_date and freeze_start_date > self.membership_end_date:
            raise ValidationError(
                {"freeze_start_date": "Dondurma başlangıcı mevcut üyelik bitiş tarihinden sonra olamaz."}
            )

        return cleaned_data
