from django.contrib import admin

from members.models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "full_name_display",
        "email",
        "phone",
        "membership_status_display",
        "balance_due_display",
        "created_at",
    )
    search_fields = ("first_name", "last_name", "email", "phone")
    list_filter = ("created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("memberships__plan", "memberships__payments")

    @admin.display(description="Ad Soyad")
    def full_name_display(self, obj):
        return obj.full_name

    @admin.display(description="Üyelik durumu")
    def membership_status_display(self, obj):
        return obj.current_membership_status

    @admin.display(description="Kalan borç")
    def balance_due_display(self, obj):
        return f"₺{obj.balance_due:.2f}"
