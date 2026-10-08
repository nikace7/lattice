from django.core.management.base import BaseCommand

from modules.conversations.tasks import recover_answers
from modules.documents.indexing import recover_indexes
from modules.documents.lifecycle import purge_documents
from modules.documents.tasks import recover_extractions


class Command(BaseCommand):
    help = "Recover expired attempts and replay pending source purges."

    def handle(self, *args, **options):
        recover_extractions()
        recover_indexes()
        recover_answers()
        purge_documents()
        self.stdout.write("Recovery batch completed.")
