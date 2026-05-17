from django.contrib import admin

from payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "membership",
        "amount",
        "payment_method",
        "payment_date",
        "status",
        "voided_at",
    )
    list_filter = ("status", "payment_method", "payment_date")
    search_fields = ("member__first_name", "member__last_name", "membership__plan__name")
    autocomplete_fields = ("membership",)
    fields = ("membership", "amount", "payment_date", "payment_method", "status", "voided_at", "note")
    readonly_fields = ("status", "voided_at")
    list_select_related = ("member", "membership__plan")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "membership":
            formfield.help_text = "Üye bilgisi seçilen üyelikten otomatik alınır."
        return formfield

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:
            readonly_fields.extend(["membership", "amount", "payment_date", "payment_method"])
        return tuple(dict.fromkeys(readonly_fields))

    def save_model(self, request, obj, form, change):
        if obj.membership_id:
            obj.member = obj.membership.member
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        obj.delete()

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()
