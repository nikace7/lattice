from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from modules.workspaces.access import can_write, membership_for

from .models import Document, IndexVersion, SourceBlock


class IndexData(serializers.ModelSerializer):
    chunkCount = serializers.IntegerField(source="chunk_count")
    canRetry = serializers.BooleanField(source="can_retry")
    semantic = serializers.SerializerMethodField()

    class Meta:
        model = IndexVersion
        fields = ["state", "active", "chunkCount", "error", "canRetry", "semantic"]
        read_only_fields = fields

    def get_semantic(self, obj) -> bool:
        return obj.profile["provider"] != "NONE"


class UploadInput(serializers.Serializer):
    uploadId = serializers.UUIDField()
    file = serializers.FileField()
    ocrLanguage = serializers.ChoiceField(choices=["eng", "nep", "eng+nep"], default="eng")


class ReviewInput(serializers.Serializer):
    expectedRevision = serializers.IntegerField(min_value=1)
    excludedPages = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=100), max_length=100
    )
    reason = serializers.CharField(max_length=1000, allow_blank=False)

    def validate_excludedPages(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Choose each excluded page only once.")
        return sorted(value)


class DocumentData(serializers.ModelSerializer):
    index = serializers.SerializerMethodField()
    collectionId = serializers.UUIDField(source="collection_id")
    sourceId = serializers.UUIDField(source="source.id")
    kind = serializers.CharField(source="source.kind")
    byteSize = serializers.IntegerField(source="source.byte_size")
    sha256 = serializers.CharField(source="source.sha256")
    state = serializers.CharField(source="source.job.state")
    error = serializers.CharField(source="source.job.error")
    retryable = serializers.BooleanField(source="source.job.can_retry")
    ocrLanguage = serializers.CharField(source="source.ocr_language")
    pageReports = serializers.SerializerMethodField()
    excludedPages = serializers.SerializerMethodField()
    reviewReason = serializers.SerializerMethodField()
    pageCount = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    canWrite = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Document
        fields = [
            "index",
            "id",
            "title",
            "collectionId",
            "sourceId",
            "revision",
            "kind",
            "byteSize",
            "sha256",
            "state",
            "error",
            "retryable",
            "ocrLanguage",
            "pageReports",
            "excludedPages",
            "reviewReason",
            "pageCount",
            "warnings",
            "canWrite",
            "createdAt",
        ]
        read_only_fields = fields

    @extend_schema_field(IndexData(allow_null=True))
    def get_index(self, obj):
        extraction = getattr(obj.source, "extraction", None)
        index = getattr(extraction, "index", None)
        return IndexData(index).data if index else None

    def get_pageCount(self, obj) -> int:
        return obj.source.extraction.page_count if hasattr(obj.source, "extraction") else 0

    def get_warnings(self, obj) -> list[str]:
        return obj.source.extraction.warnings if hasattr(obj.source, "extraction") else []

    def get_pageReports(self, obj) -> list[dict]:
        return obj.source.extraction.page_reports if hasattr(obj.source, "extraction") else []

    def get_excludedPages(self, obj) -> list[int]:
        return obj.source.extraction.excluded_pages if hasattr(obj.source, "extraction") else []

    def get_reviewReason(self, obj) -> str:
        return obj.source.extraction.review_reason if hasattr(obj.source, "extraction") else ""

    def get_canWrite(self, obj) -> bool:
        return can_write(
            obj.collection,
            membership_for(self.context["request"].user, obj.collection.workspace_id),
        )


class BlockData(serializers.ModelSerializer):
    originalText = serializers.CharField(source="original_text")
    spanMap = serializers.JSONField(source="span_map")

    class Meta:
        model = SourceBlock
        fields = ["id", "position", "text", "originalText", "locator", "spanMap"]
        read_only_fields = fields
