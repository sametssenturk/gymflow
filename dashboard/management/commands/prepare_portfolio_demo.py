import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from dashboard.demo_seed import seed_demo_data


TRUTHY_VALUES = {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Create a demo admin user and reseed the operational demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("PORTFOLIO_DEMO_USERNAME", "demo-admin"),
            help="Demo admin username.",
        )
        parser.add_argument(
            "--password",
            default=os.getenv("PORTFOLIO_DEMO_PASSWORD"),
            help="Demo admin password. Defaults to PORTFOLIO_DEMO_PASSWORD.",
        )
        parser.add_argument(
            "--email",
            default=os.getenv("PORTFOLIO_DEMO_EMAIL", "demo@gymflow.local"),
            help="Demo admin email address.",
        )
        parser.add_argument(
            "--members",
            type=int,
            default=int(os.getenv("PORTFOLIO_DEMO_MEMBER_COUNT", "160")),
            help="Number of member records to seed.",
        )
        parser.add_argument(
            "--reset-all-data",
            action="store_true",
            default=os.getenv("PORTFOLIO_DEMO_RESET_ALL_DATA", "0").lower() in TRUTHY_VALUES,
            help="Delete member, membership, payment, and plan records before seeding.",
        )
        parser.add_argument(
            "--preserve-plans",
            action="store_true",
            default=os.getenv("PORTFOLIO_DEMO_PRESERVE_PLANS", "0").lower() in TRUTHY_VALUES,
            help="Keep existing membership plans when resetting operational data.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        if not password:
            raise CommandError(
                "Demo admin password is required. Pass --password or set PORTFOLIO_DEMO_PASSWORD."
            )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"],
            defaults={
                "email": options["email"],
                "role": user_model.Role.ADMIN,
            },
        )
        user.email = options["email"]
        user.role = user_model.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        summary = seed_demo_data(
            total_members=options["members"],
            reset_all_data=options["reset_all_data"],
            preserve_plans=options["preserve_plans"],
        )

        verb = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo admin {verb}: {user.username} | "
                f"{summary['members']} members, {summary['memberships']} memberships, "
                f"{summary['payments']} payments ready."
            )
        )
