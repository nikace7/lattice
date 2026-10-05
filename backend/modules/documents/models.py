import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField

LEASE_DURATION = timedelta(seconds=90)


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
    ocr_language = models.CharField(
        max_length=7,
        default="eng",
        choices=[("eng", "English"), ("nep", "Nepali"), ("eng+nep", "English + Nepali")],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class ExtractionJob(models.Model):
    class State(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        EXTRACTING = "EXTRACTING", "Extracting"
        EXTRACTED = "EXTRACTED", "Text extracted"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        REVIEWED = "REVIEWED", "Review accepted"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    source = models.OneToOneField(SourceVersion, on_delete=models.CASCADE, related_name="job")
    state = models.CharField(max_length=12, choices=State.choices, default=State.QUEUED)
    attempt = models.UUIDField(default=uuid.uuid4)
    error = models.CharField(max_length=240, blank=True)
    retryable = models.BooleanField(default=False)
    recoveries = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source_id}: {self.state}"

    @property
    def lease_expired(self):
        return (
            self.state in {"QUEUED", "EXTRACTING"}
            and self.updated_at <= timezone.now() - LEASE_DURATION
        )

    @property
    def can_retry(self):
        return (
            self.state == "CANCELLED"
            or (self.state == "FAILED" and self.retryable)
            or self.lease_expired
        )


class ExtractionVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.OneToOneField(
        SourceVersion, on_delete=models.CASCADE, related_name="extraction"
    )
    parser_version = models.CharField(max_length=80)
    page_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list)
    page_reports = models.JSONField(default=list)
    excluded_pages = models.JSONField(default=list)
    review_reason = models.CharField(max_length=1000, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
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


class IndexVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # R3 has one immutable profile per extraction; shadow profile migration belongs to R6.
    extraction = models.OneToOneField(
        ExtractionVersion, on_delete=models.CASCADE, related_name="index"
    )
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    profile = models.JSONField()
    chunker = models.CharField(max_length=80)
    state = models.CharField(
        max_length=12,
        default="QUEUED",
        choices=[
            (state, state.title())
            for state in ["QUEUED", "CHUNKING", "EMBEDDING", "READY", "FAILED", "CANCELLED"]
        ],
    )
    active = models.BooleanField(default=False)
    attempt = models.UUIDField(default=uuid.uuid4)
    recoveries = models.PositiveSmallIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(active=False) | models.Q(state="READY"),
                name="active_index_ready",
            )
        ]

    def __str__(self):
        return f"{self.extraction_id}: {self.state}"

    @property
    def lease_expired(self):
        return (
            self.state in {"QUEUED", "CHUNKING", "EMBEDDING"}
            and self.updated_at <= timezone.now() - LEASE_DURATION
        )

    @property
    def can_retry(self):
        return self.state in {"FAILED", "CANCELLED"} or self.lease_expired


class Chunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index = models.ForeignKey(IndexVersion, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField()
    text = models.TextField()
    sha256 = models.CharField(max_length=64)
    spans = models.JSONField()
    token_count = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["index", "position"], name="unique_index_chunk")
        ]

    def __str__(self):
        return f"{self.index_id}: {self.position}"


class Embedding384(models.Model):
    chunk = models.OneToOneField(
        Chunk, on_delete=models.CASCADE, primary_key=True, related_name="embedding"
    )
    vector = VectorField(dimensions=384)

    def __str__(self):
        return str(self.chunk_id)
