from rest_framework import serializers

from pipeline.grounding import bounded_text
from pipeline.ranking import normalize_query

from .models import Conversation


class QuestionInput(serializers.Serializer):
    conversationId = serializers.UUIDField()
    idempotencyKey = serializers.UUIDField()
    question = serializers.CharField(max_length=4000)
    collectionIds = serializers.ListField(
        child=serializers.UUIDField(), max_length=100, required=False
    )
    replacesTurnId = serializers.UUIDField(required=False)

    def validate_question(self, value):
        try:
            value = normalize_query(value)
            bounded_text(value, 4000)
            return value
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error


class ConversationData(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Conversation
        fields = ["id", "title", "createdAt"]


class FeedbackInput(serializers.Serializer):
    helpful = serializers.BooleanField()


class ConversationExportData(serializers.Serializer):
    filename = serializers.CharField()
    markdown = serializers.CharField()


class CitationSpanData(serializers.Serializer):
    blockId = serializers.UUIDField()
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    location = serializers.JSONField()


class CitationData(serializers.Serializer):
    evidenceId = serializers.CharField()
    chunkId = serializers.UUIDField()
    documentId = serializers.UUIDField()
    sourceId = serializers.UUIDField()
    indexId = serializers.UUIDField()
    title = serializers.CharField()
    partial = serializers.BooleanField()
    quote = serializers.CharField()
    chunkStart = serializers.IntegerField()
    chunkEnd = serializers.IntegerField()
    spans = CitationSpanData(many=True)


class AnswerBlockData(serializers.Serializer):
    text = serializers.CharField()
    citations = CitationData(many=True)


class AnswerData(serializers.Serializer):
    status = serializers.CharField()
    blocks = AnswerBlockData(many=True)
    repaired = serializers.BooleanField()
    omittedPassages = serializers.IntegerField()


class TurnData(serializers.Serializer):
    id = serializers.UUIDField()
    conversationId = serializers.UUIDField()
    question = serializers.CharField()
    state = serializers.CharField()
    sequence = serializers.IntegerField()
    createdAt = serializers.DateTimeField()
    answer = AnswerData(allow_null=True)
    unavailable = serializers.BooleanField()
    helpful = serializers.BooleanField(allow_null=True, required=False)
    error = serializers.CharField(allow_blank=True)
    collectionIds = serializers.ListField(child=serializers.UUIDField())


class SourceQuoteSpanData(CitationSpanData):
    text = serializers.CharField()


class SourceQuoteData(CitationData):
    kind = serializers.CharField()
    sourceNumber = serializers.IntegerField()
    olderVersion = serializers.BooleanField()
    spans = SourceQuoteSpanData(many=True)


class AnswerCapabilityData(serializers.Serializer):
    enabled = serializers.BooleanField()
    message = serializers.CharField()
