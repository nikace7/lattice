from pathlib import Path

from django.conf import settings


def source_directory(source):
    # Only server-generated UUIDs form storage paths; filenames are display metadata.
    return Path(settings.STORAGE_ROOT) / "sources" / str(source.pk)


def source_path(source):
    return source_directory(source) / "original"
