from django.shortcuts import get_object_or_404

from modules.workspaces.access import readable_collections

from .models import Document, SourceVersion


def readable_documents(user):
    return Document.objects.filter(
        collection__in=readable_collections(user), deleted_at__isnull=True
    ).select_related("collection")


def readable_source(user, source_id):
    return get_object_or_404(
        SourceVersion.objects.select_related("document", "extraction"),
        pk=source_id,
        purge_requested_at__isnull=True,
        document__in=readable_documents(user),
    )
