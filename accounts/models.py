from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Yönetici")

    username = models.CharField(
        _("Kullanıcı adı"),
        max_length=150,
        unique=True,
        help_text=_(
            "Zorunlu. 150 karakter veya daha az. Harf, rakam ve @/./+/-/_ kullanabilirsiniz."
        ),
        validators=[UnicodeUsernameValidator()],
        error_messages={
            "unique": _("Bu kullanıcı adına sahip bir kullanıcı zaten var."),
        },
    )
    first_name = models.CharField(_("Ad"), max_length=150, blank=True)
    last_name = models.CharField(_("Soyad"), max_length=150, blank=True)
    email = models.EmailField(_("E-posta"), blank=True)
    role = models.CharField(_("Rol"), max_length=20, choices=Role.choices, default=Role.ADMIN)
    phone = models.CharField(_("Telefon"), max_length=32, blank=True)

    class Meta:
        verbose_name = _("Kullanıcı")
        verbose_name_plural = _("Kullanıcılar")

    def save(self, *args, **kwargs):
        self.role = self.Role.ADMIN
        self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def role_label(self) -> str:
        return _("Yönetici")
