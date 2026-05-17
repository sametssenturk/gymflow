from django.core.management.base import BaseCommand

from dashboard.demo_seed import seed_demo_data


class Command(BaseCommand):
    help = "Seed a realistic operational dataset based on the current active plan prices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--members",
            type=int,
            default=160,
            help="Create or refresh this many member records.",
        )

    def handle(self, *args, **options):
        summary = seed_demo_data(total_members=options["members"])
        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready: "
                f"{summary['members']} members, {summary['memberships']} memberships, "
                f"{summary['payments']} payments."
            )
        )
