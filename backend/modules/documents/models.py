import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey("knowledge_collections.Collection", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class SourceVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # R2 has one immutable source per document; replacement/version selection is R6.
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="source")
    filename = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=4,
        choices=[("PDF", "PDF"), ("DOCX", "Word document"), ("TXT", "Text"), ("MD", "Markdown")],
    )
    byte_size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class ExtractionJob(models.Model):
    class State(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        EXTRACTING = "EXTRACTING", "Extracting"
        EXTRACTED = "EXTRACTED", "Text extracted"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        FAILED = "FAILED", "Failed"

    source = models.OneToOneField(SourceVersion, on_delete=models.CASCADE, related_name="job")
    state = models.CharField(max_length=12, choices=State.choices, default=State.QUEUED)
    attempt = models.UUIDField(default=uuid.uuid4)
    error = models.CharField(max_length=240, blank=True)
    retryable = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source_id}: {self.state}"


class ExtractionVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.OneToOneField(
        SourceVersion, on_delete=models.CASCADE, related_name="extraction"
    )
    parser_version = models.CharField(max_length=80)
    page_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class SourceBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(
        ExtractionVersion, on_delete=models.CASCADE, related_name="blocks"
    )
    position = models.PositiveIntegerField()
    original_text = models.TextField()
    text = models.TextField()
    locator = models.JSONField()
    span_map = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["extraction", "position"], name="unique_source_block")
        ]

    def __str__(self):
        return f"{self.extraction_id}: {self.position}"
