from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


class MembershipPlan(models.Model):
    name = models.CharField(_("Paket adı"), max_length=120)
    duration_days = models.PositiveIntegerField(_("Süre (gün)"))
    price = models.DecimalField(_("Fiyat"), max_digits=10, decimal_places=2)
    description = models.TextField(_("Açıklama"), blank=True)
    is_active = models.BooleanField(_("Aktif"), default=True)
    created_at = models.DateTimeField(_("Oluşturulma tarihi"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Güncellenme tarihi"), auto_now=True)

    class Meta:
        ordering = ["price", "name"]
        constraints = [
            models.CheckConstraint(
                check=Q(duration_days__gt=0),
                name="membership_plan_duration_days_positive",
            ),
            models.CheckConstraint(
                check=Q(price__gt=0),
                name="membership_plan_price_positive",
            ),
        ]
        verbose_name = _("Üyelik Paketi")
        verbose_name_plural = _("Üyelik Paketleri")

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.duration_days is not None and self.duration_days <= 0:
            errors["duration_days"] = _("Paket süresi sıfırdan büyük olmalıdır.")
        if self.price is not None and self.price <= 0:
            errors["price"] = _("Paket fiyatı sıfırdan büyük olmalıdır.")
        if errors:
            raise ValidationError(errors)

    @property
    def duration_label(self):
        return f"{self.duration_days} gün"


class Membership(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", _("Planlandı")
        ACTIVE = "ACTIVE", _("Aktif")
        EXPIRED = "EXPIRED", _("Süresi Doldu")
        PAUSED = "PAUSED", _("Donduruldu")

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name=_("Üye"),
    )
    plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name=_("Paket"),
    )
    agreed_price = models.DecimalField(
        _("Üyelik ücreti"),
        max_digits=10,
        decimal_places=2,
        default=0,
        editable=False,
    )
    start_date = models.DateField(_("Başlangıç tarihi"))
    end_date = models.DateField(_("Bitiş tarihi"), blank=True, null=True)
    freeze_start_date = models.DateField(_("Dondurma başlangıcı"), blank=True, null=True)
    freeze_end_date = models.DateField(_("Dondurma bitişi"), blank=True, null=True)
    status = models.CharField(
        _("Durum"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    notes = models.TextField(_("Notlar"), blank=True)
    created_at = models.DateTimeField(_("Oluşturulma tarihi"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Güncellenme tarihi"), auto_now=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        verbose_name = _("Üyelik")
        verbose_name_plural = _("Üyelikler")

    def __str__(self):
        return self.display_label()

    def display_label(self, include_balance=False):
        label = (
            f"{self.member.full_name} - {self.plan.name} "
            f"({self.period_label}, {self.get_status_display()})"
        )
        if include_balance:
            label = f"{label} | Kalan ₺{self.balance_due:.2f}"
        return label

    @property
    def period_label(self):
        start_label = self.start_date.strftime("%d.%m.%Y") if self.start_date else "Başlangıç yok"
        end_label = self.end_date.strftime("%d.%m.%Y") if self.end_date else "Bitiş yok"
        return f"{start_label} - {end_label}"

    def _get_structure_change_errors(self):
        if not self.pk:
            return {}

        original_membership = (
            type(self)
            .objects.only(
                "member_id",
                "plan_id",
                "start_date",
                "end_date",
                "status",
                "freeze_start_date",
                "freeze_end_date",
            )
            .filter(pk=self.pk)
            .first()
        )
        if not original_membership:
            return {}

        changed_fields = []
        if self.member_id != original_membership.member_id:
            changed_fields.append("member")
        if self.plan_id != original_membership.plan_id:
            changed_fields.append("plan")
        if self.start_date != original_membership.start_date:
            changed_fields.append("start_date")
        if self.end_date != original_membership.end_date:
            changed_fields.append("end_date")
        if not changed_fields:
            return {}

        today = timezone.localdate()
        has_payments = original_membership.payments.exists()
        is_freeze_transition = (
            changed_fields == ["end_date"]
            and (
                self.freeze_start_date != original_membership.freeze_start_date
                or self.freeze_end_date != original_membership.freeze_end_date
                or self.status == self.Status.PAUSED
            )
        )
        if is_freeze_transition:
            return {}

        has_freeze_history = bool(
            original_membership.freeze_start_date
            or original_membership.freeze_end_date
            or original_membership.status == self.Status.PAUSED
        )
        has_started = bool(
            original_membership.start_date and original_membership.start_date <= today
        )
        is_historical = bool(
            original_membership.end_date and original_membership.end_date < today
        ) or original_membership.status == self.Status.EXPIRED

        error_message = None
        if has_payments:
            error_message = _(
                "Bu üyeliğe ödeme işlendiği için paket veya tarih bilgileri değiştirilemez. "
                "Finansal geçmişi korumak için yeni üyelik açın."
            )
        elif has_freeze_history:
            error_message = _(
                "Bu üyelikte dondurma geçmişi olduğu için paket veya tarih bilgileri değiştirilemez. "
                "Geçmişi korumak için yeni üyelik açın."
            )
        elif has_started or is_historical:
            error_message = _(
                "Başlamış veya geçmiş üyeliklerin paket ya da tarih bilgileri değiştirilemez. "
                "Hatalı kayıt için üyeliği silip yeniden açın."
            )

        if not error_message:
            return {}
        return {field_name: error_message for field_name in changed_fields}

    def clean(self):
        structure_errors = self._get_structure_change_errors()
        if structure_errors:
            raise ValidationError(structure_errors)

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("Bitiş tarihi başlangıç tarihinden önce olamaz.")})
        if self.member_id and self.status in {self.Status.ACTIVE, self.Status.PAUSED, self.Status.PLANNED}:
            today = timezone.localdate()
            is_open = self.end_date is None or self.end_date >= today
            if is_open:
                open_memberships = type(self).objects.filter(
                    member_id=self.member_id,
                    status__in=[
                        self.Status.ACTIVE,
                        self.Status.PAUSED,
                        self.Status.PLANNED,
                    ],
                ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
                if self.pk:
                    open_memberships = open_memberships.exclude(pk=self.pk)
                if open_memberships.exists():
                    raise ValidationError(
                        {
                            "member": _(
                                "Bu üyenin aktif, planlı ya da dondurulmuş bir üyeliği var."
                            )
                        }
                    )

    def get_total_paid(self, exclude_payment_id=None):
        from payments.models import Payment

        prefetched_payments = getattr(self, "_prefetched_objects_cache", {}).get("payments")
        if prefetched_payments is not None:
            return sum(
                (
                    payment.amount
                    for payment in prefetched_payments
                    if payment.status == Payment.Status.ACTIVE
                    if not exclude_payment_id or payment.pk != exclude_payment_id
                ),
                Decimal("0.00"),
            )
        payments = self.payments.filter(status=Payment.Status.ACTIVE)
        if exclude_payment_id:
            payments = payments.exclude(pk=exclude_payment_id)
        total = payments.aggregate(total=models.Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def total_paid(self):
        return self.get_total_paid()

    def remaining_balance(self, exclude_payment_id=None):
        remaining = self.agreed_price - self.get_total_paid(exclude_payment_id=exclude_payment_id)
        return max(remaining, Decimal("0.00"))

    @property
    def balance_due(self):
        return self.remaining_balance()

    @property
    def overpaid_amount(self):
        overpaid = self.get_total_paid() - self.agreed_price
        return max(overpaid, Decimal("0.00"))

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)

        def add_update_field(field_name):
            if update_fields is not None:
                update_fields.add(field_name)

        original_plan_id = None
        if self.pk:
            original_plan_id = type(self).objects.filter(pk=self.pk).values_list("plan_id", flat=True).first()
        if self.plan_id and (self._state.adding or original_plan_id != self.plan_id or not self.agreed_price):
            self.agreed_price = self.plan.price
            add_update_field("agreed_price")
        if not self.end_date and self.start_date and self.plan_id:
            self.end_date = self.start_date + timedelta(days=self.plan.duration_days)
            add_update_field("end_date")
        today = timezone.localdate()
        original_status = self.status
        if self.status == self.Status.PAUSED and self.freeze_end_date and self.freeze_end_date < today:
            if self.end_date and self.end_date < today:
                self.status = self.Status.EXPIRED
            else:
                self.status = self.Status.ACTIVE
        if self.status != self.Status.PAUSED:
            if self.end_date and self.end_date < today:
                self.status = self.Status.EXPIRED
            elif self.start_date and self.start_date > today:
                self.status = self.Status.PLANNED
            elif self.start_date and (self.end_date is None or self.end_date >= today):
                self.status = self.Status.ACTIVE
        if self.status != original_status:
            add_update_field("status")
        if update_fields is not None:
            kwargs["update_fields"] = update_fields
        self.full_clean()
        super().save(*args, **kwargs)

    def freeze(self, freeze_start_date, freeze_end_date):
        if not self.end_date:
            raise ValidationError({"end_date": _("Bu üyelik için bitiş tarihi bulunmuyor.")})
        if freeze_end_date < freeze_start_date:
            raise ValidationError({"freeze_end_date": _("Dondurma bitiş tarihi başlangıç tarihinden önce olamaz.")})
        if freeze_end_date > self.end_date:
            raise ValidationError({"freeze_end_date": _("Dondurma bitiş tarihi mevcut üyelik bitiş tarihini aşamaz.")})

        freeze_days = (freeze_end_date - freeze_start_date).days + 1
        self.end_date = self.end_date + timedelta(days=freeze_days)
        self.status = self.Status.PAUSED
        self.freeze_start_date = freeze_start_date
        self.freeze_end_date = freeze_end_date
        return freeze_days

    @classmethod
    def sync_lifecycle(cls):
        today = timezone.localdate()
        now = timezone.now()
        cls.objects.filter(status=cls.Status.ACTIVE, end_date__lt=today).update(
            status=cls.Status.EXPIRED,
            updated_at=now,
        )
        cls.objects.filter(
            status=cls.Status.PLANNED,
            start_date__lte=today,
            end_date__gte=today,
        ).update(status=cls.Status.ACTIVE, updated_at=now)
        cls.objects.filter(status=cls.Status.PLANNED, end_date__lt=today).update(
            status=cls.Status.EXPIRED,
            updated_at=now,
        )
        cls.objects.filter(
            status=cls.Status.PAUSED,
            freeze_end_date__lt=today,
            end_date__gte=today,
        ).update(status=cls.Status.ACTIVE, updated_at=now)
        cls.objects.filter(
            status=cls.Status.PAUSED,
            freeze_end_date__lt=today,
            end_date__lt=today,
        ).update(status=cls.Status.EXPIRED, updated_at=now)

    @classmethod
    def sync_expired(cls):
        cls.sync_lifecycle()

    @cached_property
    def is_current(self):
        today = timezone.localdate()
        return (
            self.status == self.Status.ACTIVE
            and self.start_date <= today
            and (self.end_date is None or self.end_date >= today)
        )

    @property
    def days_remaining(self):
        if not self.end_date:
            return None
        return max((self.end_date - timezone.localdate()).days, 0)

    @property
    def status_badge_class(self):
        if self.status == self.Status.ACTIVE:
            if self.days_remaining is not None and self.days_remaining <= 7:
                return "warning text-dark"
            return "success"
        if self.status == self.Status.PLANNED:
            return "primary"
        if self.status == self.Status.EXPIRED:
            return "secondary"
        if self.status == self.Status.PAUSED:
            return "info text-dark"
        return "secondary"
