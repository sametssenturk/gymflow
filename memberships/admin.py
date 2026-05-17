from django.contrib import admin

from memberships.models import Membership, MembershipPlan


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_days", "price", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "plan",
        "date_range",
        "agreed_price",
        "balance_due_display",
        "status",
    )
    list_filter = ("status", "plan")
    search_fields = ("member__first_name", "member__last_name", "plan__name")
    autocomplete_fields = ("member", "plan")
    list_select_related = ("member", "plan")

    @admin.display(description="Tarih aralığı", ordering="start_date")
    def date_range(self, obj):
        end_date = obj.end_date.strftime("%d.%m.%Y") if obj.end_date else "-"
        return f"{obj.start_date:%d.%m.%Y} - {end_date}"

    @admin.display(description="Kalan borç")
    def balance_due_display(self, obj):
        return f"₺{obj.balance_due:.2f}"
