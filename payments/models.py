from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", _("Nakit")
        CARD = "CARD", _("Kart")

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Geçerli")
        VOIDED = "VOIDED", _("İptal Edildi")

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("Üye"),
    )
    membership = models.ForeignKey(
        "memberships.Membership",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("Üyelik"),
    )
    amount = models.DecimalField(_("Tutar"), max_digits=10, decimal_places=2)
    payment_date = models.DateField(_("Ödeme tarihi"), default=timezone.localdate)
    payment_method = models.CharField(
        _("Ödeme yöntemi"),
        max_length=20,
        choices=Method.choices,
        default=Method.CASH,
    )
    status = models.CharField(
        _("Kayıt durumu"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    voided_at = models.DateTimeField(_("İptal tarihi"), blank=True, null=True)
    note = models.TextField(_("Not"), blank=True)
    created_at = models.DateTimeField(_("Oluşturulma tarihi"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Güncellenme tarihi"), auto_now=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        verbose_name = _("Ödeme")
        verbose_name_plural = _("Ödemeler")

    def __str__(self):
        return f"{self.member.full_name} - {self.amount}"

    def _get_immutable_field_errors(self):
        if not self.pk:
            return {}

        original_payment = (
            type(self)
            .objects.only(
                "member_id",
                "membership_id",
                "amount",
                "payment_date",
                "payment_method",
                "status",
                "voided_at",
            )
            .filter(pk=self.pk)
            .first()
        )
        if not original_payment:
            return {}

        if original_payment.status == self.Status.VOIDED:
            return {
                "status": _(
                    "İptal edilmiş ödeme kayıtları yeniden düzenlenemez."
                )
            }

        changed_fields = []
        if self.member_id != original_payment.member_id:
            changed_fields.append("member")
        if self.membership_id != original_payment.membership_id:
            changed_fields.append("membership")
        if self.amount != original_payment.amount:
            changed_fields.append("amount")
        if self.payment_date != original_payment.payment_date:
            changed_fields.append("payment_date")
        if self.payment_method != original_payment.payment_method:
            changed_fields.append("payment_method")

        if not changed_fields:
            return {}

        message = _(
            "Finansal geçmişi korumak için ödeme tutarı, tarihi, yöntemi veya bağlı üyelik değiştirilemez. "
            "Hatalı kayıt için ödemeyi iptal edip yeni kayıt açın."
        )
        return {field_name: message for field_name in changed_fields}

    def clean(self):
        immutable_errors = self._get_immutable_field_errors()
        if immutable_errors:
            raise ValidationError(immutable_errors)

        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": _("Ödeme tutarı sıfırdan büyük olmalı.")})
        if self.payment_date and self.payment_date > timezone.localdate():
            raise ValidationError({"payment_date": _("Ödeme tarihi gelecekte olamaz.")})
        if self.member_id and self.membership_id and self.membership.member_id != self.member_id:
            raise ValidationError({"membership": _("Seçilen üyelik, seçilen üyeye ait değil.")})
        if self.status == self.Status.VOIDED and not self.pk:
            raise ValidationError({"status": _("Yeni ödeme kaydı doğrudan iptal durumunda oluşturulamaz.")})
        if self.membership_id and self.amount is not None and self.status == self.Status.ACTIVE:
            remaining = self.membership.remaining_balance(exclude_payment_id=self.pk)
            if self.amount > remaining:
                raise ValidationError(
                    {
                        "amount": _(
                            "Ödeme tutarı kalan borcu aşamaz. Kalan tutar: ₺%(remaining)s"
                        )
                        % {"remaining": f"{remaining:.2f}"}
                    }
                )

    def save(self, *args, **kwargs):
        from memberships.models import Membership

        with transaction.atomic():
            if self.membership_id:
                self.membership = (
                    Membership.objects.select_related("member")
                    .select_for_update()
                    .get(pk=self.membership_id)
                )
                if not self.member_id:
                    self.member = self.membership.member
            self.full_clean()
            super().save(*args, **kwargs)

    def void(self):
        if not self.pk or self.status == self.Status.VOIDED:
            return
        self.status = self.Status.VOIDED
        self.voided_at = timezone.now()
        self.save(update_fields=["status", "voided_at", "updated_at"])

    def delete(self, using=None, keep_parents=False):
        if not self.pk:
            return super().delete(using=using, keep_parents=keep_parents)
        if self.status != self.Status.VOIDED:
            self.void()
        return (1, {f"{self._meta.app_label}.{self.__class__.__name__}": 1})

    @property
    def method_label(self):
        return self.get_payment_method_display()

    @property
    def is_active_record(self):
        return self.status == self.Status.ACTIVE

    @property
    def status_label(self):
        return self.get_status_display()
