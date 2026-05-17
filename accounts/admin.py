from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.forms import CustomUserCreationForm
from accounts.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    add_form = CustomUserCreationForm
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "staff_status",
        "active_status",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    fieldsets = (
        ("Kimlik Bilgileri", {"fields": ("username", "password")}),
        ("Kişisel Bilgiler", {"fields": ("first_name", "last_name", "email")}),
        ("Ek Bilgiler", {"fields": ("role", "phone")}),
        (
            "İzinler",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Önemli Tarihler", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            "Yeni Kullanıcı",
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "email",
                    "role",
                    "phone",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    search_fields = ("username", "first_name", "last_name", "email", "phone")

    @admin.display(boolean=True, description="Yetkili")
    def staff_status(self, obj):
        return obj.is_staff

    @admin.display(boolean=True, description="Aktif")
    def active_status(self, obj):
        return obj.is_active
