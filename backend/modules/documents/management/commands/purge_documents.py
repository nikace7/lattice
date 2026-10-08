from django.core.management.base import BaseCommand

from modules.documents.lifecycle import purge_documents, reapply_tombstones


class Command(BaseCommand):
    help = "Purge up to 100 tombstoned sources; reapply current deletion journals after restore."

    def add_arguments(self, parser):
        parser.add_argument("--reapply-tombstones", action="store_true")

    def handle(self, *args, **options):
        if options["reapply_tombstones"]:
            reapply_tombstones()
        purge_documents()
        self.stdout.write("Purge batch completed.")
