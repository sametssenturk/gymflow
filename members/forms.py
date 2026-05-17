from django import forms

from core.forms import BootstrapModelForm
from members.models import Member


class MemberForm(BootstrapModelForm):
    class Meta:
        model = Member
        fields = ["first_name", "last_name", "email", "phone", "photo", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return ""

        existing_members = Member.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            existing_members = existing_members.exclude(pk=self.instance.pk)
        if existing_members.exists():
            raise forms.ValidationError("Bu e-posta başka bir üyede kayıtlı.")
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""

        existing_members = Member.objects.filter(phone=phone)
        if self.instance and self.instance.pk:
            existing_members = existing_members.exclude(pk=self.instance.pk)
        if existing_members.exists():
            raise forms.ValidationError("Bu telefon numarası başka bir üyede kayıtlı.")
        return phone
