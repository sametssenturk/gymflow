from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


User = get_user_model()


class AdminLocalizationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="superadmin",
            password="Admin12345!",
            email="admin@example.com",
            role=User.Role.ADMIN,
        )
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)

    def test_admin_index_uses_turkish_branding(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "GymFlow Yönetim Paneli")
        self.assertContains(response, "Kimlik Doğrulama")
        self.assertContains(response, "Üye Yönetimi")
        self.assertContains(response, "Üyelikler")
        self.assertContains(response, "Ödemeler")

    def test_admin_user_add_form_labels_are_turkish(self):
        response = self.client.get(reverse("admin:accounts_customuser_add"))
        self.assertContains(response, "Kullanıcı adı")
        self.assertContains(response, "Ad")
        self.assertContains(response, "Soyad")
        self.assertContains(response, "E-posta")
        self.assertContains(response, "Rol")
        self.assertContains(response, "Telefon")

    def test_member_admin_add_form_labels_are_turkish(self):
        response = self.client.get(reverse("admin:members_member_add"))
        self.assertContains(response, "Ad")
        self.assertContains(response, "Soyad")
        self.assertContains(response, "Profil fotoğrafı")
        self.assertContains(response, "Notlar")


class AdminCrudSmokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="superadmin",
            password="Admin12345!",
            email="admin@example.com",
            role=User.Role.ADMIN,
        )
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.today = timezone.localdate()

    def test_admin_member_plan_membership_and_payment_crud(self):
        member_add = self.client.post(
            reverse("admin:members_member_add"),
            {
                "first_name": "Admin",
                "last_name": "Üye",
                "email": "admin.uye@example.com",
                "phone": "5551002000",
                "notes": "Admin test kaydı",
                "_save": "Save",
            },
        )
        self.assertEqual(member_add.status_code, 302)
        member = Member.objects.get(email="admin.uye@example.com")

        member_change = self.client.post(
            reverse("admin:members_member_change", args=[member.pk]),
            {
                "first_name": "Admin",
                "last_name": "Üye",
                "email": "admin.uye.yeni@example.com",
                "phone": "5551002001",
                "notes": "Güncellendi",
                "_save": "Save",
            },
        )
        self.assertEqual(member_change.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.email, "admin.uye.yeni@example.com")
        self.assertEqual(member.phone, "5551002001")

        plan_add = self.client.post(
            reverse("admin:memberships_membershipplan_add"),
            {
                "name": "Aylık",
                "duration_days": 30,
                "price": "500.00",
                "description": "Admin test paketi",
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(plan_add.status_code, 302)
        plan = MembershipPlan.objects.get(name="Aylık")

        membership_add = self.client.post(
            reverse("admin:memberships_membership_add"),
            {
                "member": member.pk,
                "plan": plan.pk,
                "start_date": self.today.isoformat(),
                "end_date": "",
                "status": Membership.Status.ACTIVE,
                "notes": "Admin üyelik",
                "_save": "Save",
            },
        )
        self.assertEqual(membership_add.status_code, 302)
        membership = Membership.objects.get(member=member, plan=plan)
        self.assertIsNotNone(membership.end_date)

        payment_add = self.client.post(
            reverse("admin:payments_payment_add"),
            {
                "member": member.pk,
                "membership": membership.pk,
                "amount": "150.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Admin tahsilat",
                "_save": "Save",
            },
        )
        self.assertEqual(payment_add.status_code, 302)
        payment = Payment.objects.get(note="Admin tahsilat")

        payment_change = self.client.post(
            reverse("admin:payments_payment_change", args=[payment.pk]),
            {
                "membership": membership.pk,
                "amount": "150.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "status": Payment.Status.ACTIVE,
                "voided_at_0": "",
                "voided_at_1": "",
                "note": "Admin tahsilat güncel",
                "_save": "Save",
            },
        )
        self.assertEqual(payment_change.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, 150)
        self.assertEqual(payment.payment_method, Payment.Method.CARD)
        self.assertEqual(payment.note, "Admin tahsilat güncel")

        payment_delete_page = self.client.get(reverse("admin:payments_payment_delete", args=[payment.pk]))
        self.assertEqual(payment_delete_page.status_code, 200)
        payment_delete = self.client.post(
            reverse("admin:payments_payment_delete", args=[payment.pk]),
            {"post": "yes"},
        )
        self.assertEqual(payment_delete.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VOIDED)

        membership_delete_page = self.client.get(reverse("admin:memberships_membership_delete", args=[membership.pk]))
        self.assertEqual(membership_delete_page.status_code, 200)
        membership_delete = self.client.post(
            reverse("admin:memberships_membership_delete", args=[membership.pk]),
            {"post": "yes"},
        )
        self.assertEqual(membership_delete.status_code, 200)
        self.assertTrue(Membership.objects.filter(pk=membership.pk).exists())

        plan_delete_page = self.client.get(reverse("admin:memberships_membershipplan_delete", args=[plan.pk]))
        self.assertEqual(plan_delete_page.status_code, 200)
        plan_delete = self.client.post(
            reverse("admin:memberships_membershipplan_delete", args=[plan.pk]),
            {"post": "yes"},
        )
        self.assertEqual(plan_delete.status_code, 200)
        self.assertTrue(MembershipPlan.objects.filter(pk=plan.pk).exists())

    def test_admin_payment_form_rejects_overpayment_on_create_and_locks_financial_updates(self):
        member = Member.objects.create(
            first_name="Test",
            last_name="Üye",
            email="test.uye@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Altı Yüzlük",
            duration_days=30,
            price="600.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        first_payment = self.client.post(
            reverse("admin:payments_payment_add"),
            {
                "member": member.pk,
                "membership": membership.pk,
                "amount": "400.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CASH,
                "note": "İlk ödeme",
                "_save": "Save",
            },
        )
        self.assertEqual(first_payment.status_code, 302)

        overpay_create = self.client.post(
            reverse("admin:payments_payment_add"),
            {
                "member": member.pk,
                "membership": membership.pk,
                "amount": "250.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Fazla ödeme",
                "_save": "Save",
            },
        )
        self.assertEqual(overpay_create.status_code, 200)
        self.assertContains(overpay_create, "Ödeme tutarı kalan borcu aşamaz.")
        self.assertEqual(Payment.objects.filter(membership=membership, status=Payment.Status.ACTIVE).count(), 1)

        second_payment = self.client.post(
            reverse("admin:payments_payment_add"),
            {
                "member": member.pk,
                "membership": membership.pk,
                "amount": "200.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Kalan ödeme",
                "_save": "Save",
            },
        )
        self.assertEqual(second_payment.status_code, 302)
        payment = Payment.objects.get(note="Kalan ödeme")

        locked_update = self.client.post(
            reverse("admin:payments_payment_change", args=[payment.pk]),
            {
                "membership": membership.pk,
                "amount": "250.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "status": Payment.Status.ACTIVE,
                "voided_at_0": "",
                "voided_at_1": "",
                "note": "Kalan ödeme güncel",
                "_save": "Save",
            },
        )
        self.assertEqual(locked_update.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, 200)

    def test_admin_add_buttons_support_add_another_and_continue(self):
        add_another_response = self.client.post(
            reverse("admin:members_member_add"),
            {
                "first_name": "Ece",
                "last_name": "Arslan",
                "email": "ece.addanother@example.com",
                "phone": "5551002002",
                "notes": "Add another testi",
                "_addanother": "Save and add another",
            },
        )
        self.assertEqual(add_another_response.status_code, 302)
        self.assertEqual(add_another_response["Location"], reverse("admin:members_member_add"))
        self.assertTrue(Member.objects.filter(email="ece.addanother@example.com").exists())

        continue_response = self.client.post(
            reverse("admin:members_member_add"),
            {
                "first_name": "Eren",
                "last_name": "Kaya",
                "email": "eren.continue@example.com",
                "phone": "5551002003",
                "notes": "Continue testi",
                "_continue": "Save and continue editing",
            },
        )
        self.assertEqual(continue_response.status_code, 302)
        member = Member.objects.get(email="eren.continue@example.com")
        self.assertEqual(
            continue_response["Location"],
            reverse("admin:members_member_change", args=[member.pk]),
        )
