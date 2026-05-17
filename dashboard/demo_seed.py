from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
import shutil

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from members.models import Member
from memberships.models import Membership, MembershipPlan
from payments.models import Payment


DEMO_EMAIL_DOMAIN = "@gymflow.local"
DATASET_START_DATE = date(2024, 1, 2)

FIRST_NAMES = [
    "Ayşe",
    "Mehmet",
    "Elif",
    "Efe",
    "Merve",
    "Deniz",
    "Selin",
    "Bora",
    "Derya",
    "Can",
    "Zeynep",
    "Mert",
    "İrem",
    "Emir",
    "Buse",
    "Kerem",
    "Sena",
    "Arda",
    "Nehir",
    "Okan",
    "Ceren",
    "Burak",
    "Melis",
    "Kaan",
    "Yağmur",
    "Tolga",
    "Eylül",
    "Onur",
    "Aslı",
    "Baran",
    "Gizem",
    "Umut",
    "Naz",
    "Serkan",
    "Defne",
    "Alp",
    "Sude",
    "Doruk",
    "Aylin",
    "Berk",
]

LAST_NAMES = [
    "Yılmaz",
    "Kaya",
    "Demir",
    "Çetin",
    "Şahin",
    "Kaplan",
    "Koç",
    "Aydın",
    "Öztürk",
    "Yıldız",
    "Polat",
    "Arslan",
    "Bulut",
    "Aslan",
    "Taş",
    "Güneş",
    "Aksoy",
    "Sarı",
    "Tekin",
    "Karaca",
    "Eren",
    "Kurt",
    "Bozkurt",
    "Doğan",
    "Özdemir",
    "Korkmaz",
    "Ergin",
    "Uçar",
    "Kılıç",
    "Avcı",
    "Çelik",
    "Yalçın",
    "Sezer",
    "Turan",
    "Bilgin",
    "Kara",
    "Işık",
    "Acar",
    "Güler",
    "Başar",
]


@dataclass(frozen=True)
class DemoPlanSpec:
    name: str
    duration_days: int
    fallback_price: Decimal


DEMO_PLAN_SPECS = (
    DemoPlanSpec("Aylık", 30, Decimal("550.00")),
    DemoPlanSpec("3 Aylık", 90, Decimal("1500.00")),
    DemoPlanSpec("Yıllık", 365, Decimal("5200.00")),
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _whole_lira(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1")).quantize(Decimal("0.01"))


def _current_or_default_plan(spec: DemoPlanSpec) -> MembershipPlan:
    plan = (
        MembershipPlan.objects.filter(name=spec.name)
        .order_by("-is_active", "-updated_at", "-id")
        .first()
    )
    if plan is None:
        return MembershipPlan.objects.create(
            name=spec.name,
            duration_days=spec.duration_days,
            price=spec.fallback_price,
            description=f"{spec.duration_days} günlük GymFlow üyelik paketi",
            is_active=True,
        )

    updates = []
    if plan.duration_days != spec.duration_days:
        plan.duration_days = spec.duration_days
        updates.append("duration_days")
    if not plan.description:
        plan.description = f"{spec.duration_days} günlük GymFlow üyelik paketi"
        updates.append("description")
    if not plan.is_active:
        plan.is_active = True
        updates.append("is_active")
    if updates:
        plan.save(update_fields=updates + ["updated_at"])
    return plan


def reset_portfolio_business_data():
    reset_portfolio_demo_data(preserve_plans=False)


def reset_portfolio_demo_data(preserve_plans: bool = False):
    Payment.objects.all().delete()
    Membership.objects.all().delete()
    Member.objects.all().delete()
    if not preserve_plans:
        MembershipPlan.objects.all().delete()

    photo_root = Path(settings.MEDIA_ROOT) / "members" / "photos"
    if photo_root.exists():
        shutil.rmtree(photo_root, ignore_errors=True)


def _demo_plans() -> list[MembershipPlan]:
    active_plans = list(
        MembershipPlan.objects.filter(is_active=True).order_by("duration_days", "price", "name")
    )
    if active_plans:
        return active_plans
    return [_current_or_default_plan(spec) for spec in DEMO_PLAN_SPECS]


def _weighted_plans(plans: list[MembershipPlan]) -> list[MembershipPlan]:
    weighted = []
    for plan in plans:
        if plan.duration_days <= 45:
            weight = 5
        elif plan.duration_days <= 120:
            weight = 4
        elif plan.duration_days <= 220:
            weight = 3
        else:
            weight = 2
        weighted.extend([plan] * weight)
    return weighted or plans


def _is_annual_plan(plan: MembershipPlan) -> bool:
    return plan.duration_days >= 300 or "yıl" in plan.name.casefold()


def _split_annual_payment(total_due: Decimal, installment_count: int) -> list[Decimal]:
    total_due = _whole_lira(total_due)
    if installment_count <= 1:
        return [total_due]
    if installment_count == 2:
        first = _whole_lira(total_due * Decimal("0.50"))
        return [first, _money(total_due - first)]

    first = _whole_lira(total_due * Decimal("0.40"))
    second = _whole_lira(total_due * Decimal("0.30"))
    return [first, second, _money(total_due - first - second)]


def _payment_amounts_for(membership: Membership, index: int, period_index: int) -> list[Decimal]:
    if not _is_annual_plan(membership.plan):
        return [_whole_lira(membership.agreed_price)]

    pattern = (1, 2, 2, 3, 1, 2)
    installment_count = pattern[(index + period_index) % len(pattern)]
    amounts = _split_annual_payment(membership.agreed_price, installment_count)

    today = timezone.localdate()
    has_open_balance = (
        membership.start_date >= today - timedelta(days=75)
        and membership.end_date
        and membership.end_date >= today
        and installment_count > 1
        and (index + period_index) % 8 == 0
    )
    if has_open_balance:
        return amounts[:-1]
    return amounts


def _payment_date_for(start_date: date, payment_index: int) -> date:
    payment_date = start_date + timedelta(days=payment_index * 30)
    return min(payment_date, timezone.localdate())


def _payment_method(seed: int) -> str:
    return Payment.Method.CARD if seed % 4 else Payment.Method.CASH


def _maybe_freeze_membership(membership: Membership, seed: int):
    today = timezone.localdate()
    if membership.plan.duration_days < 60 or seed % 5:
        return
    if not membership.end_date or membership.start_date > today - timedelta(days=25):
        return

    if membership.end_date >= today + timedelta(days=7):
        freeze_start = max(membership.start_date + timedelta(days=12), today - timedelta(days=2))
        if freeze_start > today:
            freeze_start = today
        freeze_end = min(freeze_start + timedelta(days=6), membership.end_date)
    else:
        freeze_start = max(membership.start_date + timedelta(days=18), today - timedelta(days=28))
        freeze_end = freeze_start + timedelta(days=6)

    if freeze_start <= today and freeze_start <= freeze_end <= membership.end_date:
        membership.freeze(freeze_start, freeze_end)
        membership.notes = (
            "Operasyon veri seti\n"
            f"Dondurma: {freeze_start:%d.%m.%Y} - {freeze_end:%d.%m.%Y}"
        )
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


def _create_payment(
    member: Member,
    membership: Membership,
    amount: Decimal,
    payment_date: date,
    payment_index: int,
    seed: int,
):
    return Payment.objects.create(
        member=member,
        membership=membership,
        amount=amount,
        payment_date=payment_date,
        payment_method=_payment_method(seed + payment_index),
        note=f"Tahsilat {membership.start_date:%Y%m}-{payment_index}",
    )


def _create_membership_payments(
    member: Member,
    membership: Membership,
    index: int,
    period_index: int,
) -> int:
    if membership.start_date > timezone.localdate():
        return 0

    created_payments = 0
    amounts = _payment_amounts_for(membership, index, period_index)
    for payment_index, amount in enumerate(amounts):
        payment_date = _payment_date_for(membership.start_date, payment_index)
        payment = _create_payment(
            member=member,
            membership=membership,
            amount=amount,
            payment_date=payment_date,
            payment_index=payment_index + 1,
            seed=index + period_index,
        )
        created_payments += 1

        if payment_index == 0 and (index + period_index) % 37 == 0:
            payment.void()
            _create_payment(
                member=member,
                membership=membership,
                amount=amount,
                payment_date=min(payment_date + timedelta(days=1), timezone.localdate()),
                payment_index=payment_index + 2,
                seed=index + period_index + 11,
            )
            created_payments += 1

    return created_payments


def _member_created_at(join_date: date, index: int):
    created_time = time(hour=9 + (index % 9), minute=(index * 7) % 60)
    created_at = datetime.combine(join_date, created_time)
    return timezone.make_aware(created_at, timezone.get_current_timezone())


def seed_demo_data(
    total_members: int = 160,
    reset_all_data: bool = False,
    preserve_plans: bool = False,
):
    today = timezone.localdate()
    dataset_days = max((today - DATASET_START_DATE).days, 1)

    with transaction.atomic():
        if reset_all_data:
            reset_portfolio_demo_data(preserve_plans=preserve_plans)
        else:
            demo_members = Member.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN)
            Payment.objects.filter(member__in=demo_members).delete()
            Membership.objects.filter(member__in=demo_members).delete()
            demo_members.delete()

        plans = _demo_plans()
        weighted_plans = _weighted_plans(plans)

        created_members = 0
        created_memberships = 0
        created_payments = 0

        for index in range(total_members):
            member_number = index + 1
            join_offset = (index * 11 + (index // 7) * 5) % dataset_days
            join_date = DATASET_START_DATE + timedelta(days=join_offset)
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(index * 5) % len(LAST_NAMES)]
            email = f"member-{member_number:04d}{DEMO_EMAIL_DOMAIN}"
            phone = f"05{30 + (index % 50):02d}{1000000 + index:07d}"[-11:]

            member = Member.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                notes="Operasyon veri seti",
            )
            Member.objects.filter(pk=member.pk).update(created_at=_member_created_at(join_date, index))
            created_members += 1

            cursor = join_date
            period_index = 0
            churn_after_first_period = index % 9 == 0
            max_periods = 2 + (index % 4)

            while cursor <= today and period_index < max_periods:
                plan = weighted_plans[(index * 3 + period_index * 5) % len(weighted_plans)]
                start_date = cursor
                end_date = start_date + timedelta(days=plan.duration_days)

                membership = Membership.objects.create(
                    member=member,
                    plan=plan,
                    start_date=start_date,
                    end_date=end_date,
                    notes="Operasyon veri seti",
                    status=Membership.Status.ACTIVE,
                )
                created_memberships += 1

                _maybe_freeze_membership(membership, index + period_index)
                created_payments += _create_membership_payments(
                    member=member,
                    membership=membership,
                    index=index,
                    period_index=period_index,
                )

                if churn_after_first_period or end_date >= today:
                    break

                gap_days = 1 + ((index + period_index) % 18)
                cursor = end_date + timedelta(days=gap_days)
                period_index += 1

    Membership.sync_lifecycle()

    return {
        "members": created_members,
        "memberships": created_memberships,
        "payments": created_payments,
        "plans": {plan.name: str(plan.price) for plan in plans},
    }
