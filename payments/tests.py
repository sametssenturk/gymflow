from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


User = get_user_model()


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="StrongPass123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.user)
        today = timezone.localdate()
        self.member = Member.objects.create(
            first_name="Ayşe",
            last_name="Yılmaz",
            email="ayse@example.com",
        )
        self.other_member = Member.objects.create(
            first_name="Bora",
            last_name="Kaya",
            email="bora@example.com",
        )
        self.plan = MembershipPlan.objects.create(
            name="Premium",
            duration_days=30,
            price="300.00",
        )
        self.membership = Membership.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=27),
        )
        self.other_membership = Membership.objects.create(
            member=self.other_member,
            plan=self.plan,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=27),
        )
        self.today = today

    def _create_membership(self, price, suffix):
        member = Member.objects.create(
            first_name="Ödeme",
            last_name=str(suffix),
            email=f"payment-{Member.objects.count() + 1}@example.com",
        )
        plan = MembershipPlan.objects.create(
            name=f"Plan {suffix}",
            duration_days=30,
            price=price,
        )
        return Membership.objects.create(
            member=member,
            plan=plan,
            start_date=self.today - timedelta(days=3),
            end_date=self.today + timedelta(days=27),
        )

    def test_payment_create_history_and_debt(self):
        create_response = self.client.post(
            f"{reverse('payments:add')}?member={self.member.pk}",
            {
                "member": self.member.pk,
                "membership": self.membership.pk,
                "amount": "120.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Kart tahsilatı",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(Payment.objects.count(), 1)

        self.member.refresh_from_db()
        self.assertEqual(self.member.balance_due, Decimal("180.00"))

        detail_response = self.client.get(reverse("members:detail", args=[self.member.pk]))
        self.assertContains(detail_response, "₺180,00")

        history_response = self.client.get(reverse("payments:list"))
        self.assertContains(history_response, "Kart tahsilatı")

    def test_payment_history_shows_membership_period(self):
        Payment.objects.create(
            member=self.member,
            membership=self.membership,
            amount="120.00",
            payment_date=self.today,
            payment_method=Payment.Method.CARD,
            note="Dönem görünürlüğü",
        )

        expected_period = (
            f"{self.membership.start_date.strftime('%d.%m.%Y')} - "
            f"{self.membership.end_date.strftime('%d.%m.%Y')}"
        )

        detail_response = self.client.get(reverse("members:detail", args=[self.member.pk]))
        self.assertContains(detail_response, expected_period)

        history_response = self.client.get(reverse("payments:list"))
        self.assertContains(history_response, expected_period)

    def test_payment_rejects_overpayment_and_keeps_balance_consistent(self):
        old_plan = MembershipPlan.objects.create(
            name="Eski Borç",
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
        self.membership.delete()
        rich_plan = MembershipPlan.objects.create(
            name="Gold",
            duration_days=30,
            price="600.00",
        )
        membership = Membership.objects.create(
            member=self.member,
            plan=rich_plan,
            start_date=self.today - timedelta(days=3),
            end_date=self.today + timedelta(days=27),
        )

        first_response = self.client.post(
            reverse("payments:add"),
            {
                "member": self.member.pk,
                "membership": membership.pk,
                "amount": "400.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CASH,
                "note": "İlk ödeme",
            },
        )
        self.assertEqual(first_response.status_code, 302)

        overpay_response = self.client.post(
            reverse("payments:add"),
            {
                "member": self.member.pk,
                "membership": membership.pk,
                "amount": "250.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Fazla ödeme",
            },
        )
        self.assertEqual(overpay_response.status_code, 200)
        self.assertContains(overpay_response, "Ödeme tutarı kalan borcu aşamaz.")
        self.assertEqual(Payment.objects.filter(membership=membership).count(), 1)

        exact_response = self.client.post(
            reverse("payments:add"),
            {
                "member": self.member.pk,
                "membership": membership.pk,
                "amount": "200.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Kalan ödeme",
            },
        )
        self.assertEqual(exact_response.status_code, 302)
        self.assertEqual(Payment.objects.filter(membership=membership).count(), 2)

        self.member.refresh_from_db()
        self.assertEqual(self.member.balance_due, Decimal("300.00"))
        self.assertEqual(membership.balance_due, Decimal("0.00"))

    def test_payment_sequence_matrix_covers_common_combinations(self):
        scenarios = [
            {
                "label": "tek seferde kapatma",
                "accepted_amounts": ["600.00"],
                "rejected_amount": "1.00",
                "expected_remaining": Decimal("0.00"),
            },
            {
                "label": "parçalı ama tam kapatma",
                "accepted_amounts": ["250.00", "250.00", "100.00"],
                "rejected_amount": "5.00",
                "expected_remaining": Decimal("0.00"),
            },
            {
                "label": "yarım ödeme sonra fazla talep",
                "accepted_amounts": ["400.00"],
                "rejected_amount": "250.00",
                "expected_remaining": Decimal("200.00"),
            },
            {
                "label": "küçük adımlarla kapatma",
                "accepted_amounts": ["100.00", "150.00", "50.00", "300.00"],
                "rejected_amount": "10.00",
                "expected_remaining": Decimal("0.00"),
            },
        ]

        for index, scenario in enumerate(scenarios, start=1):
            with self.subTest(scenario=scenario["label"]):
                membership = self._create_membership("600.00", f"{index}-{scenario['label']}")

                for step, amount in enumerate(scenario["accepted_amounts"], start=1):
                    response = self.client.post(
                        reverse("payments:add"),
                        {
                            "member": membership.member.pk,
                            "membership": membership.pk,
                            "amount": amount,
                            "payment_date": self.today.isoformat(),
                            "payment_method": Payment.Method.CASH,
                            "note": f"{scenario['label']} - {step}",
                        },
                    )
                    self.assertEqual(response.status_code, 302)

                membership.refresh_from_db()
                self.assertEqual(membership.balance_due, scenario["expected_remaining"])

                reject_response = self.client.post(
                    reverse("payments:add"),
                    {
                        "member": membership.member.pk,
                        "membership": membership.pk,
                        "amount": scenario["rejected_amount"],
                        "payment_date": self.today.isoformat(),
                        "payment_method": Payment.Method.CARD,
                        "note": f"{scenario['label']} - reddedilen",
                    },
                )
                self.assertEqual(reject_response.status_code, 200)
                if scenario["expected_remaining"] > 0:
                    self.assertContains(reject_response, "Ödeme tutarı kalan borcu aşamaz.")
                else:
                    self.assertContains(
                        reject_response,
                        "Geçerli bir seçenek seçin. Bu seçenek, mevcut seçeneklerden biri değil.",
                    )
                self.assertEqual(
                    Payment.objects.filter(membership=membership, status=Payment.Status.ACTIVE).count(),
                    len(scenario["accepted_amounts"]),
                )

    def test_payment_form_limits_memberships_to_selected_member(self):
        response = self.client.get(f"{reverse('payments:add')}?member={self.member.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.member.full_name)
        self.assertContains(response, "Premium")
        self.assertContains(response, "Kalan ₺300.00")
        self.assertContains(response, "Aktif")
        self.assertNotContains(response, self.other_member.full_name)

    def test_payment_form_hides_fully_paid_memberships_on_create(self):
        Payment.objects.create(
            member=self.member,
            membership=self.membership,
            amount="300.00",
            payment_date=self.today,
            payment_method=Payment.Method.CASH,
        )

        response = self.client.get(f"{reverse('payments:add')}?member={self.member.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Premium")
        self.assertContains(response, "---------")

    def test_payment_note_can_be_updated_but_financial_fields_are_locked(self):
        payment = Payment.objects.create(
            member=self.member,
            membership=self.membership,
            amount="120.00",
            payment_date=self.today,
            payment_method=Payment.Method.CASH,
            note="Düzeltilecek ödeme",
        )

        update_response = self.client.post(
            reverse("payments:edit", args=[payment.pk]),
            {
                "member": self.member.pk,
                "membership": self.membership.pk,
                "amount": "120.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CASH,
                "note": "Yalnızca not güncellendi",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("120.00"))
        self.assertEqual(payment.payment_method, Payment.Method.CASH)
        self.assertEqual(payment.note, "Yalnızca not güncellendi")

        locked_response = self.client.post(
            reverse("payments:edit", args=[payment.pk]),
            {
                "member": self.member.pk,
                "membership": self.membership.pk,
                "amount": "150.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Finansal alanı değiştirme denemesi",
            },
        )
        self.assertEqual(locked_response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("120.00"))
        self.assertEqual(payment.payment_method, Payment.Method.CASH)

    def test_payment_model_rejects_financial_field_changes(self):
        payment = Payment.objects.create(
            member=self.member,
            membership=self.membership,
            amount="120.00",
            payment_date=self.today,
            payment_method=Payment.Method.CASH,
            note="Model testi",
        )

        payment.amount = Decimal("150.00")
        with self.assertRaisesMessage(
            ValidationError,
            "Finansal geçmişi korumak için ödeme tutarı, tarihi, yöntemi veya bağlı üyelik değiştirilemez.",
        ):
            payment.save()

        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("120.00"))

    def test_payment_delete_voids_record_and_reopens_balance(self):
        payment = Payment.objects.create(
            member=self.member,
            membership=self.membership,
            amount="120.00",
            payment_date=self.today,
            payment_method=Payment.Method.CASH,
            note="İptal edilecek ödeme",
        )

        delete_response = self.client.post(reverse("payments:delete", args=[payment.pk]))
        self.assertEqual(delete_response.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VOIDED)
        self.assertIsNotNone(payment.voided_at)
        self.assertEqual(self.membership.balance_due, Decimal("300.00"))

        detail_response = self.client.get(reverse("members:detail", args=[self.member.pk]))
        self.assertContains(detail_response, "İptal Edildi")

        list_response = self.client.get(reverse("payments:list"))
        self.assertContains(list_response, "İptal Edildi")
        self.assertContains(list_response, "₺0,00")

        add_response = self.client.get(f"{reverse('payments:add')}?member={self.member.pk}")
        self.assertContains(add_response, "Premium")

    def test_payment_rejects_mismatched_membership(self):
        response = self.client.post(
            reverse("payments:add"),
            {
                "member": self.member.pk,
                "membership": self.other_membership.pk,
                "amount": "120.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Uyumsuz tahsilat",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seçilen üyelik, seçilen üyeye ait değil.")
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_rejects_non_positive_amount(self):
        response = self.client.post(
            f"{reverse('payments:add')}?member={self.member.pk}",
            {
                "member": self.member.pk,
                "membership": self.membership.pk,
                "amount": "0.00",
                "payment_date": self.today.isoformat(),
                "payment_method": Payment.Method.CASH,
                "note": "Sıfır tutar",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ödeme tutarı sıfırdan büyük olmalı.")
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_rejects_future_payment_date(self):
        response = self.client.post(
            f"{reverse('payments:add')}?member={self.member.pk}",
            {
                "member": self.member.pk,
                "membership": self.membership.pk,
                "amount": "100.00",
                "payment_date": (self.today + timedelta(days=1)).isoformat(),
                "payment_method": Payment.Method.CARD,
                "note": "Gelecek ödeme",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ödeme tarihi gelecekte olamaz.")
        self.assertEqual(Payment.objects.count(), 0)
