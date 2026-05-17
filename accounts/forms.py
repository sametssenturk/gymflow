from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache

from accounts.models import CustomUser


class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Parola", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Parola onayı", widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ("username", "first_name", "last_name", "email", "role", "phone")
        labels = {
            "username": "Kullanıcı adı",
            "first_name": "Ad",
            "last_name": "Soyad",
            "email": "E-posta",
            "role": "Rol",
            "phone": "Telefon",
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Parolalar eşleşmiyor.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AdminAuthenticationForm(AuthenticationForm):
    max_failed_attempts = 5
    throttle_seconds = 15 * 60
    error_messages = {
        **AuthenticationForm.error_messages,
        "admin_only": "Yalnızca yönetici hesabıyla giriş yapılabilir.",
        "too_many_attempts": "Çok sayıda hatalı giriş denemesi yapıldı. Lütfen 15 dakika sonra tekrar deneyin.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control form-control-lg",
                "placeholder": "Yönetici kullanıcı adınız",
                "autocomplete": "username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control form-control-lg",
                "placeholder": "Parolanız",
                "autocomplete": "current-password",
            }
        )

    def _throttle_key(self):
        username = (self.data.get("username") or "").strip().lower()
        remote_addr = self.request.META.get("REMOTE_ADDR", "unknown") if self.request else "unknown"
        return f"admin-login:{remote_addr}:{username}"

    def clean(self):
        throttle_key = self._throttle_key()
        failed_attempts = cache.get(throttle_key, 0)
        if failed_attempts >= self.max_failed_attempts:
            raise forms.ValidationError(
                self.error_messages["too_many_attempts"],
                code="too_many_attempts",
            )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            cache.set(throttle_key, failed_attempts + 1, self.throttle_seconds)
            raise

        cache.delete(throttle_key)
        return cleaned_data

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and getattr(user, "role", None) != CustomUser.Role.ADMIN:
            raise forms.ValidationError(
                self.error_messages["admin_only"],
                code="admin_only",
            )
