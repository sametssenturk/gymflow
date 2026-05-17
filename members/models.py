from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


class Member(models.Model):
    first_name = models.CharField(_("Ad"), max_length=100)
    last_name = models.CharField(_("Soyad"), max_length=100)
    email = models.EmailField(_("E-posta"), blank=True)
    phone = models.CharField(_("Telefon"), max_length=32, blank=True)
    photo = models.ImageField(_("Profil fotoğrafı"), upload_to="members/photos/", blank=True, null=True)
    notes = models.TextField(_("Notlar"), blank=True)
    created_at = models.DateTimeField(_("Oluşturulma tarihi"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Güncellenme tarihi"), auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=~models.Q(email=""),
                name="unique_member_email_when_set",
            ),
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(phone=""),
                name="unique_member_phone_when_set",
            ),
        ]
        verbose_name = _("Üye")
        verbose_name_plural = _("Üyeler")

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email or f"{_('Üye')} #{self.pk}"

    @cached_property
    def latest_membership(self):
        return (
            self.memberships.select_related("plan")
            .order_by("-start_date", "-id")
            .first()
        )

    @cached_property
    def active_membership(self):
        from memberships.models import Membership

        today = timezone.localdate()
        return (
            self.memberships.select_related("plan")
            .filter(
                status=Membership.Status.ACTIVE,
                start_date__lte=today,
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=today))
            .order_by("-end_date", "-id")
            .first()
        )

    @cached_property
    def open_membership(self):
        from memberships.models import Membership

        today = timezone.localdate()
        return (
            self.memberships.select_related("plan")
            .filter(
                status__in=[
                    Membership.Status.ACTIVE,
                    Membership.Status.PAUSED,
                    Membership.Status.PLANNED,
                ],
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=today))
            .order_by("-end_date", "-id")
            .first()
        )

    @property
    def has_open_membership(self):
        return self.open_membership is not None

    @cached_property
    def current_membership(self):
        return self.active_membership or self.latest_membership

    @property
    def total_paid(self):
        from payments.models import Payment

        return sum(
            (
                payment.amount
                for payment in self.payments.all()
                if payment.status == Payment.Status.ACTIVE
            ),
            Decimal("0.00"),
        )

    @property
    def balance_due(self):
        return sum(
            (membership.balance_due for membership in self.memberships.all()),
            Decimal("0.00"),
        )

    @property
    def has_debt(self):
        return self.balance_due > 0

    @property
    def current_membership_status(self):
        membership = self.current_membership
        if not membership:
            return _("Kayıt yok")
        return membership.get_status_display()
