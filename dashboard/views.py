from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.utils import timezone
from django.views.generic import TemplateView

from accounts.mixins import AdminRequiredMixin

from .reporting import build_dashboard_csv_response, build_dashboard_snapshot


class DashboardView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_snapshot())
        return context


class DashboardStatsView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/stats.html"

    def get(self, request, *args, **kwargs):
        self.snapshot = build_dashboard_snapshot()
        report_format = request.GET.get("format")
        if report_format == "csv":
            return build_dashboard_csv_response(self.snapshot)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(getattr(self, "snapshot", build_dashboard_snapshot()))
        return context


class DemoDashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        def demo_member(
            pk,
            full_name,
            membership_status,
            balance_due,
            has_debt=False,
            created_days_ago=0,
            plan_name="Aylık Paket",
            end_days=24,
        ):
            return SimpleNamespace(
                pk=pk,
                full_name=full_name,
                photo=None,
                created_at=today - timedelta(days=created_days_ago),
                current_membership_status=membership_status,
                current_membership_plan=plan_name,
                current_membership_end_date=today + timedelta(days=end_days),
                has_debt=has_debt,
                balance_due=Decimal(str(balance_due)),
            )

        def demo_payment(member_full_name, amount, method_label, days_ago, note, status_label="Geçerli"):
            return SimpleNamespace(
                member=SimpleNamespace(full_name=member_full_name),
                amount=Decimal(str(amount)),
                method_label=method_label,
                payment_date=today - timedelta(days=days_ago),
                note=note,
                status_label=status_label,
            )

        demo_members = [
            demo_member(1, "Ayşe Yılmaz", "Aktif", 0, False, created_days_ago=0, plan_name="Yıllık Premium", end_days=42),
            demo_member(2, "Mehmet Kaya", "Aktif", 350, True, created_days_ago=1, plan_name="Aylık Paket", end_days=7),
            demo_member(3, "Selin Çetin", "Tahsil edildi", 0, False, created_days_ago=2, plan_name="3 Aylık Paket", end_days=61),
            demo_member(4, "Efe Şahin", "Planlandı", 0, False, created_days_ago=3, plan_name="Aylık Paket", end_days=34),
            demo_member(5, "Merve Kaplan", "Donduruldu", 120, True, created_days_ago=4, plan_name="3 Aylık Paket", end_days=19),
        ]

        demo_memberships = [
            SimpleNamespace(member=demo_members[0], plan=SimpleNamespace(name="Yıllık Premium"), period="01.05.2026 - 01.05.2027", status_label="Aktif", balance_due=Decimal("0.00")),
            SimpleNamespace(member=demo_members[1], plan=SimpleNamespace(name="Aylık Paket"), period="10.05.2026 - 09.06.2026", status_label="Aktif", balance_due=Decimal("350.00")),
            SimpleNamespace(member=demo_members[2], plan=SimpleNamespace(name="3 Aylık Paket"), period="20.04.2026 - 19.07.2026", status_label="Aktif", balance_due=Decimal("0.00")),
            SimpleNamespace(member=demo_members[3], plan=SimpleNamespace(name="Aylık Paket"), period="01.06.2026 - 01.07.2026", status_label="Planlandı", balance_due=Decimal("650.00")),
            SimpleNamespace(member=demo_members[4], plan=SimpleNamespace(name="3 Aylık Paket"), period="15.04.2026 - 18.07.2026", status_label="Donduruldu", balance_due=Decimal("120.00")),
        ]

        demo_payments = [
            demo_payment("Ayşe Yılmaz", "20000.00", "Kart", 0, "Yıllık Premium"),
            demo_payment("Mehmet Kaya", "1150.00", "Nakit", 1, "Aylık Paket kısmi ödeme"),
            demo_payment("Selin Çetin", "12600.00", "Kart", 2, "3 Aylık Paket"),
            demo_payment("Merve Kaplan", "3780.00", "Nakit", 2, "Dondurma öncesi ödeme"),
            demo_payment("Efe Şahin", "650.00", "Kart", 4, "Planlı üyelik kaporası"),
        ]

        demo_plans = [
            SimpleNamespace(name="Aylık Paket", duration_days=30, price=Decimal("650.00"), is_active=True, description="Standart aylık üyelik"),
            SimpleNamespace(name="3 Aylık Paket", duration_days=90, price=Decimal("1800.00"), is_active=True, description="Dönemlik üyelik"),
            SimpleNamespace(name="Yıllık Premium", duration_days=365, price=Decimal("20000.00"), is_active=True, description="Uzun dönem üyelik"),
            SimpleNamespace(name="Öğrenci Paketi", duration_days=30, price=Decimal("500.00"), is_active=False, description="Pasif örnek paket"),
        ]

        context.update(
            {
                "demo_mode": True,
                "user": SimpleNamespace(
                    is_authenticated=True,
                    username="demo",
                    role_label="Sadece görüntüleme",
                    get_full_name=lambda: "Demo Görünüm",
                ),
                "display_user_name": "Demo Görünüm",
                "display_user_role": "Sadece görüntüleme",
                "total_members": 248,
                "active_memberships_count": 186,
                "new_members_this_month_count": 24,
                "upcoming_expirations_count": 12,
                "payments_today_total": Decimal("18400.00"),
                "payments_month_total": Decimal("128600.00"),
                "outstanding_balance_total": Decimal("2200.00"),
                "upcoming_expirations": [
                    SimpleNamespace(
                        member=SimpleNamespace(full_name="Ayşe Yılmaz"),
                        plan=SimpleNamespace(name="YILLIK PREMİUM"),
                        start_date=today - timedelta(days=21),
                        end_date=today + timedelta(days=9),
                        days_remaining=9,
                    ),
                    SimpleNamespace(
                        member=SimpleNamespace(full_name="Merve Kaplan"),
                        plan=SimpleNamespace(name="AYLIK PAKET"),
                        start_date=today - timedelta(days=12),
                        end_date=today + timedelta(days=5),
                        days_remaining=5,
                    ),
                    SimpleNamespace(
                        member=SimpleNamespace(full_name="Efe Şahin"),
                        plan=SimpleNamespace(name="3 AYLIK PAKET"),
                        start_date=today - timedelta(days=30),
                        end_date=today + timedelta(days=12),
                        days_remaining=12,
                    ),
                ],
                "demo_members": demo_members,
                "demo_memberships": demo_memberships,
                "demo_payments": demo_payments,
                "demo_plans": demo_plans,
                "recent_members": demo_members[:3],
            }
        )
        return context
