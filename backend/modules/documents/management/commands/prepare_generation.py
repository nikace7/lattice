from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pipeline.generation import GenerationUnavailable, pin_model, prepare_tokenizer


class Command(BaseCommand):
    help = (
        "Download the pinned Qwen tokenizer and record the already-installed Ollama model digest."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--tokenizer-only", action="store_true")

    def handle(self, *args, **options):
        prepare_tokenizer(settings.MODEL_CACHE_ROOT)
        if options["tokenizer_only"]:
            self.stdout.write("Prepared pinned generation tokenizer; Ollama model is not verified.")
            return
        try:
            manifest = pin_model(settings.MODEL_CACHE_ROOT, settings.OLLAMA_BASE_URL)
        except GenerationUnavailable as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Pinned installed qwen3:4b digest: {manifest['digest']}")
