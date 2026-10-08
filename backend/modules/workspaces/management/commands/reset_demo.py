from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from modules.workspaces.demo import environment, reset


class Command(BaseCommand):
    help = "Remove marked disposable demo data; stop API, workers, beat and parser first."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--confirm", choices=["lattice_demo"])

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("Set DEMO_MODE=true for a disposable demo installation only.")
        if options["confirm"] != "lattice_demo":
            raise CommandError("Reset requires --confirm lattice_demo.")
        reset(environment())
        self.stdout.write("Marked demo data removed. Run seed_demo to create fresh demo accounts.")
