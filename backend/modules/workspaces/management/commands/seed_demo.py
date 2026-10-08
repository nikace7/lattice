import os

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from modules.identity.models import User
from modules.workspaces.demo import PERSONAS, environment, seed


class Command(BaseCommand):
    help = "Import frozen fictional sources into a marked, empty local demo installation."
    requires_system_checks = []

    def handle(self, *args, **options):
        # Check opt-in and password before any database or filesystem work.
        if not settings.DEMO_MODE:
            raise CommandError("Set DEMO_MODE=true for a disposable demo installation only.")
        password = os.environ.get("LATTICE_DEMO_PASSWORD", "")
        try:
            for persona in PERSONAS:
                validate_password(
                    password,
                    User(username=f"demo-{persona}", email=f"demo-{persona}@lattice.invalid"),
                )
            if len(password) > 128:
                raise ValidationError("Too long")
        except ValidationError as error:
            raise CommandError(
                "Set LATTICE_DEMO_PASSWORD to a strong password (8–128 characters)."
            ) from error
        created = seed(environment(), password)
        self.stdout.write(
            "Demo seeded: 4 accounts, 2 workspaces, 24 documents, 25 unprocessed sources."
            if created
            else "Demo already seeded; no data or passwords changed."
        )
