from rest_framework import serializers

from pipeline.ranking import normalize_query


class SearchInput(serializers.Serializer):
    query = serializers.CharField(max_length=4000)
    mode = serializers.ChoiceField(choices=["KEYWORD", "SEMANTIC", "HYBRID"], default="KEYWORD")
    collectionIds = serializers.ListField(
        child=serializers.UUIDField(), max_length=100, required=False
    )
    details = serializers.BooleanField(default=False)

    def validate_query(self, value):
        try:
            return normalize_query(value)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error


class SearchHitData(serializers.Serializer):
    chunkId = serializers.UUIDField()
    documentId = serializers.UUIDField()
    sourceId = serializers.UUIDField()
    indexId = serializers.UUIDField()
    title = serializers.CharField()
    text = serializers.CharField()
    partial = serializers.BooleanField()
    spans = serializers.ListField(child=serializers.JSONField())
    locations = serializers.ListField(child=serializers.JSONField())


class RankedHitData(serializers.Serializer):
    chunkId = serializers.UUIDField()
    lexicalRank = serializers.IntegerField(allow_null=True)
    vectorRank = serializers.IntegerField(allow_null=True)
    rrf = serializers.FloatField()
    lexicalScore = serializers.FloatField(allow_null=True)
    cosineDistance = serializers.FloatField(allow_null=True)


class SearchDiagnosticsData(serializers.Serializer):
    mode = serializers.CharField()
    scope = serializers.ListField(child=serializers.UUIDField())
    corpusHash = serializers.CharField()
    profileHash = serializers.CharField()
    indexIds = serializers.ListField(child=serializers.UUIDField())
    accessEpoch = serializers.IntegerField()
    elapsedMs = serializers.IntegerField()
    lexical = serializers.ListField(child=serializers.JSONField())
    vector = serializers.ListField(child=serializers.JSONField())
    selected = RankedHitData(many=True)


class SearchData(serializers.Serializer):
    runId = serializers.UUIDField()
    mode = serializers.CharField()
    results = SearchHitData(many=True)
    diagnostics = SearchDiagnosticsData(allow_null=True)
