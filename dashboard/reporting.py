from datetime import date, timedelta
from decimal import Decimal
import csv
import io
from types import SimpleNamespace

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone

from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


def _money(value):
    return value if value is not None else Decimal("0.00")


def _prefetched_memberships(member):
    memberships = list(member.memberships.all())
    memberships.sort(
        key=lambda membership: (
            membership.start_date or date.min,
            membership.pk or 0,
        ),
        reverse=True,
    )
    return memberships


def _membership_paid_total(membership):
    return sum(
        (payment.amount for payment in membership.payments.all() if payment.status == Payment.Status.ACTIVE),
        Decimal("0.00"),
    )


def _month_start(year, month):
    return date(year, month, 1)


MONTH_LABELS_TR = (
    "Oca",
    "Şub",
    "Mar",
    "Nis",
    "May",
    "Haz",
    "Tem",
    "Ağu",
    "Eyl",
    "Eki",
    "Kas",
    "Ara",
)


def _format_month_label(month_start):
    return f"{MONTH_LABELS_TR[month_start.month - 1]} {month_start.year}"


def _add_months(base_date, months):
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _build_line_chart(series, width=720, height=260, padding=32):
    values = [float(item["amount"]) for item in series]
    max_value = max(values, default=0.0)
    plot_width = width - (padding * 2)
    plot_height = height - (padding * 2)
    step = plot_width / max(len(series) - 1, 1)

    points = []
    for index, item in enumerate(series):
        value = float(item["amount"])
        ratio = (value / max_value) if max_value else 0.0
        x = padding + (index * step)
        y = height - padding - (ratio * plot_height)
        if not max_value:
            y = height - padding
        points.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "label": item["label"],
                "amount": item["amount"],
            }
        )

    if not points:
        return {"points": [], "line_path": "", "area_path": "", "max_value": Decimal("0.00")}

    line_segments = [f"M {points[0]['x']} {points[0]['y']}"]
    for point in points[1:]:
        line_segments.append(f"L {point['x']} {point['y']}")

    baseline = height - padding
    first_point = points[0]
    last_point = points[-1]
    area_path = (
        f"{' '.join(line_segments)} "
        f"L {last_point['x']} {baseline} L {first_point['x']} {baseline} Z"
    )

    return {
        "points": points,
        "line_path": " ".join(line_segments),
        "area_path": area_path,
        "max_value": _money(Decimal(str(max_value))),
    }


def build_dashboard_snapshot():
    today = timezone.localdate()
    cutoff = today + timedelta(days=14)
    month_start_date = today.replace(day=1)

    Membership.sync_lifecycle()

    members = list(
        Member.objects.prefetch_related(
            "memberships__plan",
            "memberships__payments",
            "payments",
        ).order_by("-created_at", "-id")
    )

    active_memberships = (
        Membership.objects.select_related("member", "plan")
        .filter(
            status=Membership.Status.ACTIVE,
            start_date__lte=today,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .order_by("end_date", "member__first_name")
    )

    all_payments = Payment.objects.select_related("member", "membership__plan").filter(
        payment_date__lte=today,
        status=Payment.Status.ACTIVE,
    ).order_by(
        "-payment_date",
        "-id",
    )

    member_snapshots = []
    for member in members:
        memberships = _prefetched_memberships(member)
        current_membership = next(
            (
                membership
                for membership in memberships
                if membership.status == Membership.Status.ACTIVE
                and membership.start_date <= today
                and (membership.end_date is None or membership.end_date >= today)
            ),
            None,
        ) or (memberships[0] if memberships else None)
        if current_membership:
            total_paid = sum(
                (_membership_paid_total(membership) for membership in memberships),
                Decimal("0.00"),
            )
            balance_due = sum(
                (
                    max(
                        membership.agreed_price - _membership_paid_total(membership),
                        Decimal("0.00"),
                    )
                    for membership in memberships
                ),
                Decimal("0.00"),
            )
            status_label = current_membership.get_status_display()
            plan_name = current_membership.plan.name
            end_date = current_membership.end_date
        else:
            total_paid = Decimal("0.00")
            balance_due = Decimal("0.00")
            status_label = "Kayıt yok"
            plan_name = None
            end_date = None

        member_snapshots.append(
            SimpleNamespace(
                pk=member.pk,
                full_name=member.full_name,
                photo=member.photo if member.photo else None,
                created_at=member.created_at,
                current_membership_status=status_label,
                current_membership_plan=plan_name,
                current_membership_end_date=end_date,
                total_paid=total_paid,
                balance_due=balance_due,
                has_debt=balance_due > 0,
            )
        )

    new_members_this_month_count = sum(
        1
        for member in members
        if timezone.localtime(member.created_at).date() >= month_start_date
    )

    payments_today_total = _money(
        all_payments.filter(payment_date=today).aggregate(total=Sum("amount"))["total"]
    )
    payments_month_total = _money(
        all_payments.filter(
            payment_date__year=today.year,
            payment_date__month=today.month,
        ).aggregate(total=Sum("amount"))["total"]
    )

    weekly_payment_totals = {
        row["payment_date"]: _money(row["total"])
        for row in all_payments.filter(
            payment_date__gte=today - timedelta(days=6),
            payment_date__lte=today,
        )
        .order_by()
        .values("payment_date")
        .annotate(total=Sum("amount"))
    }
    weekly_peak = max(weekly_payment_totals.values(), default=Decimal("0.00"))
    weekly_revenue_series = []
    for offset in range(6, -1, -1):
        current_day = today - timedelta(days=offset)
        amount = _money(weekly_payment_totals.get(current_day))
        height = 18 + float(amount / weekly_peak * 82) if weekly_peak > 0 else 18
        weekly_revenue_series.append(
            {
                "label": current_day.strftime("%d.%m"),
                "amount": amount,
                "height": round(height, 2),
            }
        )
    for index, item in enumerate(weekly_revenue_series):
        previous_amount = weekly_revenue_series[index - 1]["amount"] if index > 0 else Decimal("0.00")
        delta = item["amount"] - previous_amount
        item["previous_amount"] = previous_amount
        item["previous_attr"] = f"{float(previous_amount):.2f}"
        item["delta"] = delta
        item["delta_attr"] = f"{float(delta):.2f}"
        item["delta_direction"] = "up" if delta > 0 else "down" if delta < 0 else "flat"
        item["delta_abs"] = abs(delta)
    weekly_revenue_total = sum((item["amount"] for item in weekly_revenue_series), Decimal("0.00"))
    weekly_revenue_summary = {
        "total": _money(weekly_revenue_total),
        "average": _money(weekly_revenue_total / Decimal("7")) if weekly_revenue_series else Decimal("0.00"),
        "peak_day": max(weekly_revenue_series, key=lambda item: item["amount"], default=None),
    }
    weekly_revenue_chart = _build_line_chart(weekly_revenue_series)
    for index, item in enumerate(weekly_revenue_series):
        point = weekly_revenue_chart["points"][index] if weekly_revenue_chart["points"] else {"x": 0, "y": 0}
        x_attr = f"{point['x']:.2f}"
        y_attr = f"{point['y']:.2f}"
        amount_attr = f"{float(item['amount']):.2f}"
        item["x_attr"] = x_attr
        item["y_attr"] = y_attr
        item["amount_attr"] = amount_attr
        if weekly_revenue_chart["points"]:
            weekly_revenue_chart["points"][index]["x_attr"] = x_attr
            weekly_revenue_chart["points"][index]["y_attr"] = y_attr
            weekly_revenue_chart["points"][index]["amount_attr"] = amount_attr
            weekly_revenue_chart["points"][index]["previous_attr"] = item["previous_attr"]
            weekly_revenue_chart["points"][index]["delta_attr"] = item["delta_attr"]
            weekly_revenue_chart["points"][index]["delta_direction"] = item["delta_direction"]

    monthly_payment_totals = {
        (row["month"].year, row["month"].month): _money(row["total"])
        for row in all_payments.filter(
            payment_date__gte=_add_months(_month_start(today.year, today.month), -5),
        )
        .order_by()
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
    }
    monthly_peak = max(monthly_payment_totals.values(), default=Decimal("0.00"))
    monthly_revenue_series = []
    current_month_start = _month_start(today.year, today.month)
    for offset in range(5, -1, -1):
        month_start = _add_months(current_month_start, -offset)
        amount = _money(monthly_payment_totals.get((month_start.year, month_start.month)))
        height = 18 + float(amount / monthly_peak * 82) if monthly_peak > 0 else 18
        monthly_revenue_series.append(
            {
                "label": _format_month_label(month_start),
                "amount": amount,
                "height": round(height, 2),
                "month_start": month_start,
            }
        )
    for index, item in enumerate(monthly_revenue_series):
        item["share"] = round((float(item["amount"]) / float(monthly_peak) * 100), 1) if monthly_peak > 0 else 0
        previous_amount = monthly_revenue_series[index - 1]["amount"] if index > 0 else Decimal("0.00")
        delta = item["amount"] - previous_amount
        item["delta"] = delta
        item["trend_label"] = "Yükseliş" if delta > 0 else "Düşüş" if delta < 0 else "Sabit"
        item["trend_value"] = abs(delta)
    monthly_revenue_chart = _build_line_chart(monthly_revenue_series)
    monthly_revenue_total = sum((item["amount"] for item in monthly_revenue_series), Decimal("0.00"))
    monthly_has_activity = any(item["amount"] > 0 for item in monthly_revenue_series)
    monthly_average = (
        _money(monthly_revenue_total / Decimal(len(monthly_revenue_series)))
        if monthly_revenue_series
        else Decimal("0.00")
    )
    monthly_current = monthly_revenue_series[-1] if monthly_revenue_series else None
    monthly_previous = monthly_revenue_series[-2] if len(monthly_revenue_series) > 1 else None
    monthly_best = (
        max(monthly_revenue_series, key=lambda item: item["amount"], default=None)
        if monthly_has_activity
        else None
    )
    monthly_change = Decimal("0.00")
    monthly_change_label = "Sabit"
    if monthly_current and monthly_previous:
        monthly_change = monthly_current["amount"] - monthly_previous["amount"]
        monthly_change_label = (
            "Yükseliş" if monthly_change > 0 else "Düşüş" if monthly_change < 0 else "Sabit"
        )
    monthly_summary_cards = [
        {
            "label": "Son 6 ay toplam",
            "value": _money(monthly_revenue_total),
            "note": "Seçili dönem içindeki tüm tahsilatlar" if monthly_has_activity else "Bu aralıkta tahsilat kaydı yok",
            "tone": "accent",
        },
        {
            "label": "Aylık ortalama",
            "value": monthly_average,
            "note": "Bu aralıktaki ortalama gelir" if monthly_has_activity else "Hesaplanacak kayıt yok",
            "tone": "soft",
        },
        {
            "label": "Bu ay",
            "value": _money(monthly_current["amount"]) if monthly_current else Decimal("0.00"),
            "note": (
                f"{monthly_change_label} • {'+' if monthly_change >= 0 else '-'}₺{abs(monthly_change):.2f} önceki aya göre"
                if monthly_has_activity and monthly_current and monthly_previous
                else "Bu aralıkta karşılaştırma için kayıt yok"
            ),
            "tone": "warning",
        },
    ]
    monthly_highlight = {
        "label": monthly_best["label"] if monthly_best else "Kayıt yok",
        "value": _money(monthly_best["amount"]) if monthly_best else Decimal("0.00"),
        "note": "En yüksek aylık tahsilat",
    }

    membership_total_count = Membership.objects.count()
    active_memberships_count = active_memberships.count()
    planned_memberships_count = Membership.objects.filter(status=Membership.Status.PLANNED).count()
    paused_memberships_count = Membership.objects.filter(status=Membership.Status.PAUSED).count()
    expired_memberships_count = Membership.objects.filter(status=Membership.Status.EXPIRED).count()
    membership_status_breakdown = [
        {
            "label": "Aktif",
            "count": active_memberships_count,
            "color": "#57e1c6",
        },
        {
            "label": "Planlandı",
            "count": planned_memberships_count,
            "color": "#67e8f9",
        },
        {
            "label": "Donduruldu",
            "count": paused_memberships_count,
            "color": "#f0b86e",
        },
        {
            "label": "Süresi doldu",
            "count": expired_memberships_count,
            "color": "#7b88ff",
        },
    ]
    membership_breakdown_total = sum(item["count"] for item in membership_status_breakdown) or 1
    gradient_parts = []
    start = 0.0
    for item in membership_status_breakdown:
        share = (item["count"] / membership_breakdown_total) * 100
        end = start + share
        gradient_parts.append(f"{item['color']} {start:.1f}% {end:.1f}%")
        item["percent"] = round(share, 1)
        start = end
    membership_status_gradient = ", ".join(gradient_parts) if gradient_parts else "#57e1c6 0% 100%"

    payment_method_rows = []
    method_definitions = [
        (Payment.Method.CASH, "Nakit", "#57e1c6"),
        (Payment.Method.CARD, "Kart", "#7b88ff"),
    ]
    for method, label, color in method_definitions:
        row = all_payments.filter(payment_method=method).aggregate(
            count=Count("id"),
            total=Sum("amount"),
        )
        payment_method_rows.append(
            {
                "label": label,
                "count": row["count"] or 0,
                "total": _money(row["total"]),
                "color": color,
            }
        )
    payment_total_sum = sum((item["total"] for item in payment_method_rows), Decimal("0.00"))
    for item in payment_method_rows:
        item["percent"] = (
            round((item["total"] / payment_total_sum) * 100, 1)
            if payment_total_sum > 0
            else 0
        )
        item["percent_css"] = f"{item['percent']:.1f}"

    recent_payments = list(all_payments[:5])
    debt_watchlist = sorted(
        [member for member in member_snapshots if member.has_debt],
        key=lambda member: member.balance_due,
        reverse=True,
    )[:5]
    outstanding_balance_total = sum(
        (member.balance_due for member in member_snapshots),
        Decimal("0.00"),
    )
    plan_breakdown = [
        {
            "label": plan.name,
            "duration_days": plan.duration_days,
            "count": plan.membership_count,
            "revenue": _money(plan.membership_revenue),
        }
        for plan in MembershipPlan.objects.annotate(
            membership_count=Count("memberships"),
            membership_revenue=Sum("memberships__agreed_price"),
        ).order_by("-membership_count", "name")[:6]
    ]
    plan_total = sum(item["count"] for item in plan_breakdown) or 1
    for item in plan_breakdown:
        item["percent"] = round((item["count"] / plan_total) * 100, 1)

    return {
        "total_members": len(member_snapshots),
        "active_memberships_count": active_memberships_count,
        "new_members_this_month_count": new_members_this_month_count,
        "upcoming_expirations_count": active_memberships.filter(
            end_date__isnull=False,
            end_date__lte=cutoff,
        ).count(),
        "upcoming_expirations": list(
            active_memberships.filter(end_date__isnull=False, end_date__lte=cutoff)[:5]
        ),
        "recent_members": member_snapshots[:5],
        "recent_payments": recent_payments,
        "weekly_revenue_series": weekly_revenue_series,
        "weekly_revenue_chart": weekly_revenue_chart,
        "weekly_revenue_summary": weekly_revenue_summary,
        "monthly_revenue_series": monthly_revenue_series,
        "monthly_revenue_chart": monthly_revenue_chart,
        "monthly_revenue_summary": {
            "total": _money(monthly_revenue_total),
            "average": monthly_average,
            "has_activity": monthly_has_activity,
            "current": monthly_current,
            "previous": monthly_previous,
            "change": monthly_change,
            "change_label": monthly_change_label,
            "best": monthly_best,
        },
        "monthly_summary_cards": monthly_summary_cards,
        "monthly_highlight": monthly_highlight,
        "payments_today_total": payments_today_total,
        "payments_month_total": payments_month_total,
        "membership_total_count": membership_total_count,
        "membership_status_breakdown": membership_status_breakdown,
        "membership_status_gradient": membership_status_gradient,
        "payment_method_breakdown": payment_method_rows,
        "top_debt_members": debt_watchlist,
        "outstanding_balance_total": outstanding_balance_total,
        "plan_breakdown": plan_breakdown,
        "planned_memberships_count": planned_memberships_count,
        "paused_memberships_count": paused_memberships_count,
        "expired_memberships_count": expired_memberships_count,
    }


def build_dashboard_csv_response(snapshot):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Kategori", "Metrik", "Değer"])

    def write(section, metric, value):
        writer.writerow([section, metric, value])

    write("Genel", "Toplam üye", snapshot["total_members"])
    write("Genel", "Aktif üyelik", snapshot["active_memberships_count"])
    write("Genel", "Bu ay yeni üye", snapshot["new_members_this_month_count"])
    write("Genel", "Planlı üyelik", snapshot["planned_memberships_count"])
    write("Genel", "Dondurulan üyelik", snapshot["paused_memberships_count"])
    write("Genel", "Süresi dolan üyelik", snapshot["expired_memberships_count"])
    write("Finans", "Bugünkü tahsilat", f"{snapshot['payments_today_total']:.2f}")
    write("Finans", "Bu ay tahsilat", f"{snapshot['payments_month_total']:.2f}")
    write("Finans", "Açık bakiye", f"{snapshot['outstanding_balance_total']:.2f}")

    for item in snapshot["payment_method_breakdown"]:
        write("Ödeme yöntemi", item["label"], f"{item['count']} işlem / {item['total']:.2f}")

    for item in snapshot["membership_status_breakdown"]:
        write("Üyelik durumu", item["label"], f"{item['count']} kayıt")

    for item in snapshot["plan_breakdown"]:
        write("Paket", item["label"], f"{item['count']} kayıt / {item['revenue']:.2f}")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="gymflow-dashboard-rapor.csv"'
    response.write("\ufeff")
    response.write(buffer.getvalue())
    return response
