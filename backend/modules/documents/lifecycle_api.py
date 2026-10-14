from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict, Pages, check_revision, validated
from modules.audit.service import audit
from modules.workspaces.access import can_write, locked_collection, locked_membership, require_owner
from modules.workspaces.serializers import RevisionInput

from .access import readable_documents
from .lifecycle import cancel_reindex, selected_profile, start_reindex, tombstone
from .models import IndexVersion, Reindex
from .serializers import DocumentData, ReplacementInput
from .upload_api import UploadView


class ReplaceView(UploadView):
    @extend_schema(request=ReplacementInput, responses={201: DocumentData, 200: DocumentData})
    def post(self, request, document_id):
        return super().post(request, document_id=document_id)


class DeleteView(APIView):
    @extend_schema(request=RevisionInput, responses={204: None})
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to delete this document.")
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        check_revision(document, validated(RevisionInput, request))
        tombstone(document)
        audit(member.workspace, request.user, "document.deleted", document)
        return Response(status=204)


class VersionData(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.IntegerField()
    filename = serializers.CharField()
    current = serializers.BooleanField()
    pending = serializers.BooleanField()


class VersionPages(Pages):
    ordering = "-number"


class VersionsView(generics.GenericAPIView):
    serializer_class = VersionData
    pagination_class = VersionPages

    def get(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        current = set(
            IndexVersion.objects.filter(
                extraction__source__document=document, active=True
            ).values_list("extraction__source_id", flat=True)
        )
        latest = document.source.pk
        page = self.paginate_queryset(document.versions.filter(purge_requested_at__isnull=True))
        return self.get_paginated_response(
            VersionData(
                [
                    {
                        "id": source.pk,
                        "number": source.number,
                        "filename": source.filename,
                        "current": source.pk in current,
                        "pending": source.pk == latest,
                    }
                    for source in page
                ],
                many=True,
            ).data
        )


class PurgeVersionView(APIView):
    @extend_schema(request=RevisionInput, responses={204: None})
    @transaction.atomic
    def post(self, request, document_id, source_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, _ = locked_collection(request.user, document.collection_id)
        require_owner(member)
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        check_revision(document, validated(RevisionInput, request))
        source = get_object_or_404(document.versions, pk=source_id)
        if (
            source.pk == document.source.pk
            or IndexVersion.objects.filter(extraction__source=source, active=True).exists()
        ):
            raise Conflict("Only a retained, inactive source version can be purged.")
        tombstone(document, source)
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "source.purge_requested", source)
        return Response(status=204)


class ReindexInput(serializers.Serializer):
    profile = serializers.ChoiceField(choices=["E5", "NONE"])


class ReindexData(serializers.ModelSerializer):
    class Meta:
        model = Reindex
        fields = ["id", "state", "profile"]
        read_only_fields = fields


class ReindexView(APIView):
    @extend_schema(responses=ReindexData(allow_null=True))
    @transaction.atomic
    def get(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        batch = Reindex.objects.filter(workspace=member.workspace).order_by("-created_at").first()
        return Response(ReindexData(batch).data if batch else None)

    @extend_schema(request=ReindexInput, responses={202: ReindexData})
    @transaction.atomic
    def post(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        data = validated(ReindexInput, request)
        batch = start_reindex(member.workspace, request.user, selected_profile(data["profile"]))
        audit(member.workspace, request.user, "workspace.reindex_requested", batch)
        return Response(ReindexData(batch).data, status=202)

    @extend_schema(request=None, responses={204: None})
    @transaction.atomic
    def delete(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        for batch in Reindex.objects.filter(workspace=member.workspace, state="BUILDING"):
            cancel_reindex(batch)
            audit(member.workspace, request.user, "workspace.reindex_cancelled", batch)
        return Response(status=204)


class Quotas(serializers.Serializer):
    daily_answers = serializers.IntegerField(min_value=0, max_value=100)
    daily_embedding_tokens = serializers.IntegerField(min_value=0, max_value=500000)
    storage_bytes = serializers.IntegerField(min_value=0, max_value=2147483648)
    document_limit = serializers.IntegerField(min_value=0, max_value=500)


class QuotasView(APIView):
    @extend_schema(responses=Quotas)
    @transaction.atomic
    def get(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        return Response(Quotas(member.workspace).data)

    @extend_schema(request=Quotas, responses=Quotas)
    @transaction.atomic
    def put(self, request, workspace_id):
        member = locked_membership(request.user, workspace_id)
        require_owner(member)
        data = validated(Quotas, request)
        for key, value in data.items():
            setattr(member.workspace, key, value)
        member.workspace.save(update_fields=list(data))
        audit(member.workspace, request.user, "workspace.quotas_changed", member.workspace)
        return Response(Quotas(member.workspace).data)
