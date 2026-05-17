import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


User = get_user_model()


class MemberCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="StrongPass123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.user)
        self.media_root = tempfile.mkdtemp(prefix="gymflow-members-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def _image_file(self):
        buffer = BytesIO()
        image = Image.new("RGB", (1, 1), color="blue")
        image.save(buffer, format="PNG")
        return SimpleUploadedFile("member.png", buffer.getvalue(), content_type="image/png")

    def test_member_create_update_and_delete(self):
        create_data = {
            "first_name": "Ayşe",
            "last_name": "Yılmaz",
            "email": "ayse@example.com",
            "phone": "5551112233",
            "notes": "İlk kayıt",
            "photo": self._image_file(),
        }
        with override_settings(MEDIA_ROOT=self.media_root):
            create_response = self.client.post(reverse("members:add"), create_data)

        self.assertEqual(create_response.status_code, 302)
        member = Member.objects.get(first_name="Ayşe")
        self.assertTrue(member.photo.name.startswith("members/photos/"))

        detail_response = self.client.get(reverse("members:detail", args=[member.pk]))
        self.assertContains(detail_response, "Ayşe Yılmaz")

        update_data = {
            "first_name": "Ayşe",
            "last_name": "Yılmaz",
            "email": "ayse.yeni@example.com",
            "phone": "5559998877",
            "notes": "Güncellenmiş not",
        }
        update_response = self.client.post(reverse("members:edit", args=[member.pk]), update_data)
        self.assertEqual(update_response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.email, "ayse.yeni@example.com")
        self.assertEqual(member.phone, "5559998877")
        self.assertEqual(member.notes, "Güncellenmiş not")

        delete_response = self.client.post(reverse("members:delete", args=[member.pk]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())

    def test_member_list_search_filters_results(self):
        Member.objects.create(
            first_name="Arda",
            last_name="Çelik",
            email="arda@example.com",
            phone="5550001111",
        )
        Member.objects.create(
            first_name="Buse",
            last_name="Demir",
            email="buse@example.com",
            phone="5550002222",
        )

        response = self.client.get(reverse("members:list"), {"q": "Arda"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Arda Çelik")
        self.assertNotContains(response, "Buse Demir")

    def test_member_form_rejects_duplicate_contact_information(self):
        Member.objects.create(
            first_name="Var",
            last_name="Olan",
            email="mevcut@example.com",
            phone="5550003333",
        )

        response = self.client.post(
            reverse("members:add"),
            {
                "first_name": "Yeni",
                "last_name": "Üye",
                "email": "MEVCUT@example.com",
                "phone": "5550003333",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu e-posta başka bir üyede kayıtlı.")
        self.assertContains(response, "Bu telefon numarası başka bir üyede kayıtlı.")
        self.assertEqual(Member.objects.count(), 1)

    def test_member_delete_is_blocked_when_financial_records_exist(self):
        member = Member.objects.create(
            first_name="Can",
            last_name="Öztürk",
            email="can@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Klasik",
            duration_days=30,
            price="250.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
        )
        Payment.objects.create(
            member=member,
            membership=membership,
            amount="125.00",
            payment_date=timezone.localdate(),
            payment_method=Payment.Method.CASH,
            note="Kısmi ödeme",
        )

        response = self.client.post(reverse("members:delete", args=[member.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())
        self.assertTrue(Membership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(Payment.objects.exists())

    def test_membership_delete_stays_blocked_when_only_voided_payments_exist(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Arsiv",
            last_name="Odeme",
            email="arsiv@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Uclu Paket",
            duration_days=90,
            price="3750.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=plan,
            start_date=today,
            end_date=today + timedelta(days=90),
        )
        payment = Payment.objects.create(
            member=member,
            membership=membership,
            amount="3750.00",
            payment_date=today,
            payment_method=Payment.Method.CARD,
        )
        payment.void()

        response = self.client.post(
            reverse("members:membership_delete", args=[member.pk, membership.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Membership.objects.filter(pk=membership.pk).exists())
        follow_response = self.client.get(response["Location"], follow=True)
        self.assertContains(
            follow_response,
            "Bu üyelikte aktif ya da iptal edilmiş ödeme geçmişi olduğu için silinemez.",
        )

    def test_member_scoped_membership_crud_flow(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Deneme",
            last_name="Üye",
            email="demo@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Özel Paket",
            duration_days=30,
            price="450.00",
        )

        create_response = self.client.post(
            reverse("members:membership_add", args=[member.pk]),
            {
                "member": member.pk,
                "plan": plan.pk,
                "start_date": today.isoformat(),
                "end_date": "",
                "notes": "Üye kartından oluşturuldu",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        membership = Membership.objects.get(member=member, plan=plan)
        self.assertEqual(membership.end_date, today + timedelta(days=30))
        self.assertEqual(membership.agreed_price, Decimal("450.00"))

        update_response = self.client.post(
            reverse(
                "members:membership_edit",
                args=[member.pk, membership.pk],
            ),
            {
                "member": member.pk,
                "plan": plan.pk,
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=30)).isoformat(),
                "notes": "Üye kartından güncellendi",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
        self.assertEqual(membership.notes, "Üye kartından güncellendi")

        delete_response = self.client.post(
            reverse("members:membership_delete", args=[member.pk, membership.pk])
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Membership.objects.filter(pk=membership.pk).exists())

        list_response = self.client.get(reverse("members:list"))
        self.assertContains(list_response, f'href="{reverse("members:detail", args=[member.pk])}"')

    def test_member_detail_prompts_update_for_past_membership(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Geçmiş",
            last_name="Üyelik",
            email="gecmis@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Aylık",
            duration_days=30,
            price="300.00",
        )
        Membership.objects.create(
            member=member,
            plan=plan,
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=30),
            status=Membership.Status.EXPIRED,
        )

        response = self.client.get(reverse("members:detail", args=[member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yeni Üyelik")
        self.assertNotContains(response, "Son Üyeliği Güncelle")
        self.assertContains(response, "Geçmiş üyelikler korunur")

    def test_second_open_membership_is_rejected_for_same_member(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Çakışan",
            last_name="Üyelik",
            email="cakis@example.com",
        )
        first_plan = MembershipPlan.objects.create(
            name="İlk Paket",
            duration_days=30,
            price="350.00",
        )
        second_plan = MembershipPlan.objects.create(
            name="İkinci Paket",
            duration_days=30,
            price="500.00",
        )
        Membership.objects.create(
            member=member,
            plan=first_plan,
            start_date=today,
            end_date=today + timedelta(days=30),
        )

        response = self.client.post(
            reverse("members:membership_add", args=[member.pk]),
            {
                "member": member.pk,
                "plan": second_plan.pk,
                "start_date": today.isoformat(),
                "end_date": "",
                "notes": "İkinci üyelik denemesi",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aktif, planlı ya da dondurulmuş bir üyeliği var")
        self.assertEqual(Membership.objects.filter(member=member).count(), 1)

    def test_current_membership_prefers_latest_active_membership(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Deneme",
            last_name="Kullanici",
            email="demo@example.com",
        )
        old_plan = MembershipPlan.objects.create(
            name="Eski Paket",
            duration_days=30,
            price="250.00",
        )
        new_plan = MembershipPlan.objects.create(
            name="Yeni Paket",
            duration_days=30,
            price="500.00",
        )
        old_membership = Membership.objects.create(
            member=member,
            plan=old_plan,
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=30),
            status=Membership.Status.EXPIRED,
        )
        Payment.objects.create(
            member=member,
            membership=old_membership,
            amount="250.00",
            payment_date=today - timedelta(days=55),
            payment_method=Payment.Method.CASH,
            note="Eski üyelik tahsilatı",
        )
        new_membership = Membership.objects.create(
            member=member,
            plan=new_plan,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=29),
            status=Membership.Status.ACTIVE,
        )

        member.refresh_from_db()
        self.assertEqual(member.current_membership.pk, new_membership.pk)
        self.assertEqual(member.current_membership_status, "Aktif")
        self.assertEqual(member.balance_due, Decimal("500.00"))
        self.assertEqual(member.total_paid, Decimal("250.00"))

    def test_member_debt_includes_unpaid_past_memberships(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Borç",
            last_name="Takip",
            email="borc@example.com",
        )
        old_plan = MembershipPlan.objects.create(
            name="Eski Borç",
            duration_days=30,
            price="300.00",
        )
        new_plan = MembershipPlan.objects.create(
            name="Yeni Ödenmiş",
            duration_days=30,
            price="500.00",
        )
        Membership.objects.create(
            member=member,
            plan=old_plan,
            start_date=today - timedelta(days=70),
            end_date=today - timedelta(days=40),
            status=Membership.Status.EXPIRED,
        )
        new_membership = Membership.objects.create(
            member=member,
            plan=new_plan,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=29),
        )
        Payment.objects.create(
            member=member,
            membership=new_membership,
            amount="500.00",
            payment_date=today,
            payment_method=Payment.Method.CASH,
        )

        member.refresh_from_db()
        self.assertEqual(member.current_membership.pk, new_membership.pk)
        self.assertEqual(member.balance_due, Decimal("300.00"))

    def test_member_membership_edit_blocks_rewriting_paid_history(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Geçmiş",
            last_name="Koruma",
            email="koruma@example.com",
        )
        old_plan = MembershipPlan.objects.create(
            name="Eski Plan",
            duration_days=30,
            price="300.00",
        )
        new_plan = MembershipPlan.objects.create(
            name="Yeni Plan",
            duration_days=30,
            price="500.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=old_plan,
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=30),
            status=Membership.Status.EXPIRED,
        )
        Payment.objects.create(
            member=member,
            membership=membership,
            amount="150.00",
            payment_date=today - timedelta(days=55),
            payment_method=Payment.Method.CASH,
            note="Eski tahsilat",
        )

        response = self.client.post(
            reverse("members:membership_edit", args=[member.pk, membership.pk]),
            {
                "member": member.pk,
                "plan": new_plan.pk,
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=30)).isoformat(),
                "notes": "Geçmişi taşıma denemesi",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu üyeliğe ödeme işlendiği için paket veya tarih bilgileri değiştirilemez.")

        membership.refresh_from_db()
        self.assertEqual(membership.plan_id, old_plan.pk)
        self.assertEqual(
            membership.period_label,
            f"{(today - timedelta(days=60)).strftime('%d.%m.%Y')} - {(today - timedelta(days=30)).strftime('%d.%m.%Y')}",
        )

    def test_member_membership_freeze_extends_end_date_and_marks_donduruldu(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Freeze",
            last_name="Test",
            email="freeze@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Dondurulabilir",
            duration_days=30,
            price="500.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=plan,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=25),
        )

        response = self.client.post(
            reverse("members:membership_freeze", args=[member.pk, membership.pk]),
            {
                "freeze_start_date": today.isoformat(),
                "freeze_end_date": (today + timedelta(days=4)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.PAUSED)
        self.assertEqual(membership.end_date, today + timedelta(days=30))
        self.assertIn("Donduruldu:", membership.notes)

        detail_response = self.client.get(reverse("members:detail", args=[member.pk]))
        self.assertContains(detail_response, "Dondurulmuş üyelik açık")
        self.assertNotContains(detail_response, "Aktif üyelik devam ediyor")

    def test_finished_freeze_auto_reactivates_on_member_detail(self):
        today = timezone.localdate()
        member = Member.objects.create(
            first_name="Auto",
            last_name="Aktif",
            email="auto@example.com",
        )
        plan = MembershipPlan.objects.create(
            name="Dondurma Biten",
            duration_days=30,
            price="500.00",
        )
        membership = Membership.objects.create(
            member=member,
            plan=plan,
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=20),
        )
        membership.freeze_start_date = today - timedelta(days=6)
        membership.freeze_end_date = today - timedelta(days=1)
        membership.status = Membership.Status.PAUSED
        membership.save(update_fields=[
            "freeze_start_date",
            "freeze_end_date",
            "status",
            "end_date",
            "updated_at",
        ])

        response = self.client.get(reverse("members:detail", args=[member.pk]))
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
        self.assertContains(response, "Aktif")
