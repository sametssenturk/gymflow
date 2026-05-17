from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.demo_seed import DEMO_PLAN_SPECS
from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


User = get_user_model()


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="StrongPass123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.user)

        today = timezone.localdate()
        self.member_one = Member.objects.create(
            first_name="Ayşe",
            last_name="Yılmaz",
            email="ayse@example.com",
            phone="5551112233",
        )
        self.member_two = Member.objects.create(
            first_name="Mehmet",
            last_name="Kaya",
            email="mehmet@example.com",
            phone="5554445566",
        )
        Member.objects.filter(pk=self.member_two.pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        self.member_two.refresh_from_db()
        self.plan = MembershipPlan.objects.create(
            name="Premium Paket",
            duration_days=30,
            price="450.00",
        )
        self.membership = Membership.objects.create(
            member=self.member_one,
            plan=self.plan,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=10),
        )
        Payment.objects.create(
            member=self.member_one,
            membership=self.membership,
            amount="120.00",
            payment_date=today - timedelta(days=1),
            payment_method=Payment.Method.CASH,
            note="Nakit tahsilat",
        )
        Payment.objects.create(
            member=self.member_one,
            membership=self.membership,
            amount="80.00",
            payment_date=today,
            payment_method=Payment.Method.CARD,
            note="Kart tahsilat",
        )

    def test_dashboard_metrics(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_members"], 2)
        self.assertEqual(response.context["active_memberships_count"], 1)
        self.assertEqual(response.context["upcoming_expirations_count"], 1)
        self.assertEqual(response.context["new_members_this_month_count"], 1)
        self.assertEqual(response.context["payments_today_total"], Decimal("80.00"))
        self.assertEqual(response.context["payments_month_total"], Decimal("200.00"))
        self.assertEqual(len(response.context["weekly_revenue_series"]), 7)
        self.assertEqual(response.context["monthly_revenue_series"][-1]["amount"], Decimal("200.00"))
        self.assertEqual(len(response.context["payment_method_breakdown"]), 2)
        self.assertContains(response, "Bugünkü Tahsilat")
        self.assertContains(response, "Açık Bakiye")
        self.assertContains(response, "Bu Ay Yeni Üye")
        self.assertContains(response, "Yaklaşan üyelik bitişleri")
        self.assertContains(response, "Ayşe Yılmaz")
        self.assertContains(response, f'href="{reverse("members:detail", args=[self.member_one.pk])}"')
        self.assertContains(response, "Mehmet Kaya")
        self.assertContains(response, "Kayıt tarihi")
        self.assertNotContains(response, "Son 7 günün tahsilat akışı")
        self.assertNotContains(response, "Durum dağılımı")
        self.assertNotContains(response, "Ödeme akışı")
        self.assertNotContains(response, "Son Kayıtlar")
        self.assertNotContains(response, "Yakından izlenmesi gereken hesaplar")

    def test_stats_page_renders_detailed_reports(self):
        response = self.client.get(reverse("dashboard:stats"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detaylı istatistikler")
        self.assertContains(response, "Son 7 günün tahsilat akışı")
        self.assertContains(response, "dashboard-line-chart")
        self.assertContains(response, "dashboard-chart-tooltip")
        self.assertContains(response, "Aylık görünüm")
        self.assertContains(response, "dashboard-mini-chart")
        self.assertContains(response, "CSV indir")
        self.assertContains(response, "Yazdır")
        self.assertContains(response, "Ödeme yöntemleri")
        self.assertContains(response, "Paket dağılımı")
        self.assertContains(response, "Üyelik hacmi")
        self.assertContains(response, "En yeni tahsilatlar")
        self.assertContains(response, "iptaller hariç")
        self.assertContains(response, "Açık bakiye")
        self.assertContains(response, "Paketler")
        self.assertContains(response, reverse("members:detail", args=[self.member_one.pk]))
        self.assertNotContains(response, "Ödeme akışı")

    def test_stats_csv_export(self):
        response = self.client.get(reverse("dashboard:stats"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"gymflow-dashboard-rapor.csv\"", response["Content-Disposition"])
        csv_text = response.content.decode("utf-8-sig")
        self.assertIn("Toplam üye", csv_text)
        self.assertIn("Paket", csv_text)
        self.assertIn("Açık bakiye", csv_text)

    def test_anonymous_users_redirect_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_demo_dashboard_is_public_and_read_only(self):
        self.client.logout()
        response = self.client.get(reverse("demo_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demo görünüm")
        self.assertContains(response, "Toplam Üye")
        self.assertContains(response, "#demo-members")
        self.assertContains(response, "#demo-memberships")
        self.assertContains(response, "#demo-payments")
        self.assertContains(response, "#demo-packages")
        self.assertContains(response, "#demo-stats")
        self.assertContains(response, "Üye listesi önizlemesi")
        self.assertContains(response, "Yıllık Premium")
        self.assertContains(response, "Paket listesi önizlemesi")
        self.assertContains(response, "Rapor Önizlemesi")
        self.assertContains(response, "Salt okunur")
        self.assertNotContains(response, "Ana sayfa")
        self.assertNotContains(response, "Siteyi Gör")
        self.assertNotContains(response, reverse("dashboard:index"))
        self.assertNotContains(response, reverse("members:list"))
        self.assertNotContains(response, reverse("members:add"))
        self.assertNotContains(response, reverse("accounts:logout"))


class DemoSeedCommandTests(TestCase):
    def setUp(self):
        duration_map = {spec.name: spec.duration_days for spec in DEMO_PLAN_SPECS}
        self.current_prices = {
            "Aylık": Decimal("610.00"),
            "3 Aylık": Decimal("1600.00"),
            "Yıllık": Decimal("5300.00"),
        }
        for name, price in self.current_prices.items():
            MembershipPlan.objects.create(
                name=name,
                duration_days=duration_map[name],
                price=price,
                is_active=True,
            )

        legacy_member = Member.objects.create(
            first_name="Eski",
            last_name="Demo",
            email="legacy@gymflow.local",
            phone="5550000000",
        )
        legacy_plan = MembershipPlan.objects.create(
            name="Legacy",
            duration_days=30,
            price="100.00",
            is_active=False,
        )
        legacy_membership = Membership.objects.create(
            member=legacy_member,
            plan=legacy_plan,
            start_date=timezone.localdate() - timedelta(days=20),
            end_date=timezone.localdate() + timedelta(days=10),
        )
        Payment.objects.create(
            member=legacy_member,
            membership=legacy_membership,
            amount="50.00",
            payment_date=timezone.localdate() - timedelta(days=3),
            payment_method=Payment.Method.CASH,
            note="Eski demo ödeme",
        )
        self.real_member = Member.objects.create(
            first_name="Gerçek",
            last_name="Üye",
            email="real@example.com",
            phone="5551110000",
        )

    def test_seed_demo_data_reuses_current_prices_and_cleans_old_demo_members(self):
        out = StringIO()
        call_command("seed_demo_data", members=18, stdout=out)

        self.assertIn("Demo data ready", out.getvalue())
        self.assertFalse(Member.objects.filter(email="legacy@gymflow.local").exists())
        self.assertTrue(Member.objects.filter(pk=self.real_member.pk).exists())
        self.assertEqual(Member.objects.filter(email__endswith="@gymflow.local").count(), 18)

        seeded_memberships = Membership.objects.filter(member__email__endswith="@gymflow.local")
        seeded_payments = Payment.objects.filter(member__email__endswith="@gymflow.local")

        self.assertGreaterEqual(seeded_memberships.count(), 18)
        self.assertGreater(seeded_payments.count(), 0)
        self.assertTrue(seeded_memberships.filter(status=Membership.Status.PAUSED).exists())

        observed_prices = set(
            seeded_memberships.values_list("agreed_price", flat=True)
        )
        self.assertTrue(observed_prices.issubset(set(self.current_prices.values())))
        self.assertTrue(
            all(
                membership.agreed_price == membership.plan.price
                for membership in seeded_memberships.select_related("plan")
            )
        )

    def test_seed_demo_data_can_reset_all_portfolio_business_data(self):
        out = StringIO()
        call_command("seed_demo_data", members=5, stdout=out)

        self.assertTrue(Member.objects.filter(pk=self.real_member.pk).exists())

        prepare_out = StringIO()
        call_command(
            "prepare_portfolio_demo",
            username="demo-admin",
            password="TestOnlyPassword123!",
            email="demo@gymflow.local",
            members=7,
            reset_all_data=True,
            stdout=prepare_out,
        )

        admin_user = User.objects.get(username="demo-admin")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertFalse(Member.objects.filter(pk=self.real_member.pk).exists())
        self.assertEqual(Member.objects.filter(email__endswith="@gymflow.local").count(), 7)
        self.assertEqual(MembershipPlan.objects.count(), len(DEMO_PLAN_SPECS))
        self.assertIn("Demo admin", prepare_out.getvalue())

    def test_prepare_demo_can_reset_business_data_while_preserving_plans(self):
        prepare_out = StringIO()
        call_command(
            "prepare_portfolio_demo",
            username="demo-admin",
            password="TestOnlyPassword123!",
            email="demo@gymflow.local",
            members=7,
            reset_all_data=True,
            preserve_plans=True,
            stdout=prepare_out,
        )

        self.assertFalse(Member.objects.filter(pk=self.real_member.pk).exists())
        self.assertTrue(MembershipPlan.objects.filter(name="Legacy").exists())
        self.assertEqual(MembershipPlan.objects.count(), len(self.current_prices) + 1)
        self.assertEqual(Member.objects.filter(email__endswith="@gymflow.local").count(), 7)
        self.assertIn("demo-admin", prepare_out.getvalue())
