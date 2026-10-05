from django.conf import settings
from django.core.management.base import BaseCommand

from pipeline.embedding import prepare_model


class Command(BaseCommand):
    help = "Explicitly download the pinned local E5 safetensors model and tokenizer."
    requires_system_checks = []

    def handle(self, *args, **options):
        directory = prepare_model(settings.MODEL_CACHE_ROOT)
        self.stdout.write(f"Prepared pinned E5 model: {directory}")
