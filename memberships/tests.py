from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from members.models import Member
from memberships.forms import MembershipPlanForm
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


class MembershipModelTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.member = Member.objects.create(
            first_name="Ayşe",
            last_name="Yılmaz",
            email="ayse@example.com",
        )

    def test_membership_keeps_original_price_when_plan_price_changes(self):
        plan = MembershipPlan.objects.create(
            name="Sabit",
            duration_days=30,
            price="600.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        self.assertEqual(membership.agreed_price, Decimal("600.00"))

        plan.price = Decimal("900.00")
        plan.save(update_fields=["price"])

        membership.refresh_from_db()
        self.assertEqual(membership.agreed_price, Decimal("600.00"))
        self.assertEqual(membership.balance_due, Decimal("600.00"))

    def test_active_membership_keeps_old_price_and_new_membership_uses_updated_price(self):
        plan = MembershipPlan.objects.create(
            name="Kilitli",
            duration_days=30,
            price="600.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )
        Payment.objects.create(
            member=self.member,
            membership=membership,
            amount="400.00",
            payment_date=self.today,
            payment_method=Payment.Method.CASH,
            note="İlk ödeme",
        )

        plan.price = Decimal("800.00")
        plan.save(update_fields=["price"])

        membership.refresh_from_db()
        self.assertEqual(membership.agreed_price, Decimal("600.00"))
        self.assertEqual(membership.balance_due, Decimal("200.00"))

        second_member = Member.objects.create(
            first_name="Yeni",
            last_name="Üye",
            email="yeni@example.com",
        )
        second_membership = Membership.objects.create(
            member=second_member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        self.assertEqual(second_membership.agreed_price, Decimal("800.00"))
        self.assertEqual(second_membership.balance_due, Decimal("800.00"))

    def test_membership_freeze_extends_end_date_and_changes_status(self):
        plan = MembershipPlan.objects.create(
            name="Dondurma",
            duration_days=30,
            price="400.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        freeze_days = membership.freeze(
            self.today + timedelta(days=2),
            self.today + timedelta(days=6),
        )
        membership.notes = f"Donduruldu: {self.today.strftime('%d.%m.%Y')}"
        membership.save(
            update_fields=[
                "end_date",
                "freeze_start_date",
                "freeze_end_date",
                "status",
                "notes",
                "updated_at",
            ]
        )

        membership.refresh_from_db()
        self.assertEqual(freeze_days, 5)
        self.assertEqual(membership.status, Membership.Status.PAUSED)
        self.assertEqual(membership.end_date, self.today + timedelta(days=35))
        self.assertEqual(membership.freeze_start_date, self.today + timedelta(days=2))
        self.assertEqual(membership.freeze_end_date, self.today + timedelta(days=6))
        self.assertEqual(membership.status_badge_class, "info text-dark")

    def test_membership_auto_sets_end_date_from_plan_duration(self):
        plan = MembershipPlan.objects.create(
            name="Aylık",
            duration_days=45,
            price="450.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
        )

        self.assertEqual(membership.end_date, self.today + timedelta(days=45))
        self.assertEqual(membership.agreed_price, Decimal("450.00"))

    def test_membership_period_label_formats_date_range(self):
        plan = MembershipPlan.objects.create(
            name="Etiket",
            duration_days=30,
            price="450.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        expected_label = (
            f"{self.today.strftime('%d.%m.%Y')} - "
            f"{(self.today + timedelta(days=30)).strftime('%d.%m.%Y')}"
        )
        self.assertEqual(membership.period_label, expected_label)

    def test_expired_membership_does_not_block_new_membership(self):
        old_plan = MembershipPlan.objects.create(
            name="Eski",
            duration_days=30,
            price="300.00",
        )
        Membership.objects.create(
            member=self.member,
            plan=old_plan,
            start_date=self.today - timedelta(days=60),
            end_date=self.today - timedelta(days=30),
            status=Membership.Status.EXPIRED,
        )
        new_plan = MembershipPlan.objects.create(
            name="Yeni",
            duration_days=30,
            price="500.00",
        )

        membership = Membership.objects.create(
            member=self.member,
            plan=new_plan,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
        )

        self.assertEqual(membership.agreed_price, Decimal("500.00"))
        self.assertEqual(self.member.open_membership.pk, membership.pk)

    def test_future_membership_is_planned_until_start_date(self):
        plan = MembershipPlan.objects.create(
            name="Planlı",
            duration_days=30,
            price="400.00",
        )

        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today + timedelta(days=3),
        )

        self.assertEqual(membership.status, Membership.Status.PLANNED)
        self.assertEqual(self.member.current_membership_status, "Planlandı")
        self.assertTrue(self.member.has_open_membership)

    def test_model_rejects_second_open_membership_for_member(self):
        plan = MembershipPlan.objects.create(
            name="Tek Açık Kayıt",
            duration_days=30,
            price="400.00",
        )
        Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "aktif, planlı ya da dondurulmuş bir üyeliği var",
        ):
            Membership.objects.create(
                member=self.member,
                plan=plan,
                start_date=self.today + timedelta(days=1),
            )

    def test_expired_membership_cannot_be_reused_for_new_period(self):
        plan = MembershipPlan.objects.create(
            name="Yenilenen",
            duration_days=30,
            price="400.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today - timedelta(days=60),
            end_date=self.today - timedelta(days=30),
            status=Membership.Status.EXPIRED,
        )

        membership.start_date = self.today
        membership.end_date = self.today + timedelta(days=30)

        with self.assertRaisesMessage(
            ValidationError,
            "Başlamış veya geçmiş üyeliklerin paket ya da tarih bilgileri değiştirilemez.",
        ):
            membership.save()

        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.EXPIRED)
        self.assertEqual(membership.start_date, self.today - timedelta(days=60))
        self.assertEqual(membership.end_date, self.today - timedelta(days=30))

    def test_paid_membership_cannot_change_plan_or_dates(self):
        original_plan = MembershipPlan.objects.create(
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
            member=self.member,
            plan=original_plan,
            start_date=self.today - timedelta(days=15),
            end_date=self.today + timedelta(days=15),
        )
        Payment.objects.create(
            member=self.member,
            membership=membership,
            amount="150.00",
            payment_date=self.today - timedelta(days=10),
            payment_method=Payment.Method.CASH,
            note="İlk tahsilat",
        )

        membership.plan = new_plan
        membership.start_date = self.today
        membership.end_date = self.today + timedelta(days=30)

        with self.assertRaisesMessage(
            ValidationError,
            "Bu üyeliğe ödeme işlendiği için paket veya tarih bilgileri değiştirilemez.",
        ):
            membership.save()

        membership.refresh_from_db()
        self.assertEqual(membership.plan_id, original_plan.pk)
        self.assertEqual(membership.agreed_price, Decimal("300.00"))
        self.assertEqual(membership.balance_due, Decimal("150.00"))

    def test_planned_membership_without_payments_can_be_corrected(self):
        original_plan = MembershipPlan.objects.create(
            name="Planlı Paket",
            duration_days=30,
            price="300.00",
        )
        revised_plan = MembershipPlan.objects.create(
            name="Düzeltilen Paket",
            duration_days=45,
            price="450.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=original_plan,
            start_date=self.today + timedelta(days=7),
            end_date=self.today + timedelta(days=37),
            status=Membership.Status.PLANNED,
        )

        membership.plan = revised_plan
        membership.start_date = self.today + timedelta(days=10)
        membership.end_date = self.today + timedelta(days=55)
        membership.save()

        membership.refresh_from_db()
        self.assertEqual(membership.plan_id, revised_plan.pk)
        self.assertEqual(membership.agreed_price, Decimal("450.00"))
        self.assertEqual(membership.start_date, self.today + timedelta(days=10))
        self.assertEqual(membership.end_date, self.today + timedelta(days=55))
        self.assertEqual(membership.status, Membership.Status.PLANNED)

    def test_sync_lifecycle_reactivates_paused_membership_after_freeze(self):
        plan = MembershipPlan.objects.create(
            name="Kısa Dondurma",
            duration_days=30,
            price="400.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=12),
            status=Membership.Status.PAUSED,
            freeze_start_date=self.today - timedelta(days=6),
            freeze_end_date=self.today - timedelta(days=1),
        )

        Membership.sync_lifecycle()

        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
        self.assertEqual(membership.end_date, self.today + timedelta(days=12))

    def test_sync_lifecycle_expires_paused_membership_when_freeze_extends_past_end_date(self):
        plan = MembershipPlan.objects.create(
            name="Sona Gelen Dondurma",
            duration_days=30,
            price="400.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=plan,
            start_date=self.today - timedelta(days=40),
            end_date=self.today - timedelta(days=5),
            status=Membership.Status.PAUSED,
            freeze_start_date=self.today - timedelta(days=10),
            freeze_end_date=self.today - timedelta(days=6),
        )

        Membership.sync_lifecycle()

        membership.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.EXPIRED)


class MembershipPlanFormTests(TestCase):
    def test_plan_requires_positive_duration_and_price(self):
        form = MembershipPlanForm(
            data={
                "name": "Hatalı Paket",
                "duration_days": 0,
                "price": "0.00",
                "description": "",
                "is_active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Paket süresi sıfırdan büyük olmalıdır.", form.errors["duration_days"])
        self.assertIn("Paket fiyatı sıfırdan büyük olmalıdır.", form.errors["price"])
