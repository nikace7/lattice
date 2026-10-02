from rest_framework import serializers

from modules.workspaces.access import can_write, membership_for

from .models import Document, SourceBlock


class UploadInput(serializers.Serializer):
    uploadId = serializers.UUIDField()
    file = serializers.FileField()


class DocumentData(serializers.ModelSerializer):
    collectionId = serializers.UUIDField(source="collection_id")
    sourceId = serializers.UUIDField(source="source.id")
    kind = serializers.CharField(source="source.kind")
    byteSize = serializers.IntegerField(source="source.byte_size")
    sha256 = serializers.CharField(source="source.sha256")
    state = serializers.CharField(source="source.job.state")
    error = serializers.CharField(source="source.job.error")
    retryable = serializers.BooleanField(source="source.job.retryable")
    pageCount = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    canWrite = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Document
        fields = [
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
            "pageCount",
            "warnings",
            "canWrite",
            "createdAt",
        ]
        read_only_fields = fields

    def get_pageCount(self, obj) -> int:
        return obj.source.extraction.page_count if hasattr(obj.source, "extraction") else 0

    def get_warnings(self, obj) -> list[str]:
        return obj.source.extraction.warnings if hasattr(obj.source, "extraction") else []

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
