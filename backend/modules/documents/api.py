import hashlib
import uuid
from datetime import timedelta
from pathlib import PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict, Pages
from modules.workspaces.access import can_write, membership_for, readable_collections
from modules.workspaces.api import audit, locked_collection, validated
from modules.workspaces.serializers import RevisionInput
from pipeline.source_parser import MAX_BYTES, InvalidSource, validate_bytes

from .models import Document, ExtractionJob, SourceBlock, SourceVersion
from .serializers import BlockData, DocumentData, UploadInput
from .storage import source_directory, source_path
from .tasks import enqueue


def readable_documents(user):
    return Document.objects.filter(collection__in=readable_collections(user)).select_related(
        "collection", "source", "source__job", "source__extraction"
    )


def readable_source(user, source_id):
    return get_object_or_404(
        SourceVersion.objects.select_related("document", "extraction"),
        pk=source_id,
        document__in=readable_documents(user),
    )


class DocumentsView(generics.ListAPIView):
    serializer_class = DocumentData

    def get_queryset(self):
        membership_for(self.request.user, self.kwargs["workspace_id"])
        queryset = readable_documents(self.request.user).filter(
            collection__workspace_id=self.kwargs["workspace_id"]
        )
        collection = self.request.query_params.get("collectionId")
        if collection:
            try:
                queryset = queryset.filter(collection_id=uuid.UUID(collection))
            except ValueError as error:
                raise ValidationError("Choose a valid collection.") from error
        return queryset


class UploadView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(request=UploadInput, responses={201: DocumentData, 200: DocumentData})
    def post(self, request, collection_id):
        # Check contribution rights before persisting the source in private storage.
        collection = get_object_or_404(readable_collections(request.user), pk=collection_id)
        if not can_write(collection, membership_for(request.user, collection.workspace_id)):
            raise PermissionDenied("You need contribution access to upload here.")
        raw_data = request.data
        if getattr(request._request, "upload_too_large", False):
            raise ValidationError("The upload exceeds 25 MiB.")
        data = UploadInput(data=raw_data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        filename = PurePosixPath(upload.name.replace("\\", "/")).name
        if len(filename) > 200 or upload.size > MAX_BYTES:
            raise ValidationError(
                "Use a filename under 200 characters and a file no larger than 25 MiB."
            )
        suffix = PurePosixPath(filename).suffix.lower()
        kind = {".pdf": "PDF", ".txt": "TXT"}.get(suffix)
        content = upload.read(MAX_BYTES + 1)
        try:
            validate_bytes(content, kind)
        except InvalidSource as error:
            raise ValidationError(str(error)) from error
        digest = hashlib.sha256(content).hexdigest()
        saved_path = None
        try:
            with transaction.atomic():
                member, collection = locked_collection(request.user, collection_id)
                if not can_write(collection, member):
                    raise PermissionDenied("Contribution access changed. Refresh and try again.")
                existing = Document.objects.filter(pk=data.validated_data["uploadId"]).first()
                if existing:
                    if (
                        existing.collection_id != collection.pk
                        or existing.created_by_id != request.user.pk
                        or existing.source.sha256 != digest
                        or existing.source.filename != filename
                    ):
                        raise Conflict(
                            "This upload identifier was already used for a different file."
                        )
                    return Response(DocumentData(existing, context={"request": request}).data)
                sources = SourceVersion.objects.filter(
                    document__collection__workspace=member.workspace
                )
                total = sources.aggregate(total=Sum("byte_size"))["total"] or 0
                if (
                    sources.count() >= 500
                    or total + len(content) > settings.MAX_WORKSPACE_STORAGE_BYTES
                ):
                    raise ValidationError(
                        "This workspace has reached its document or storage limit."
                    )
                document = Document.objects.create(
                    id=data.validated_data["uploadId"],
                    collection=collection,
                    title=filename,
                    created_by=request.user,
                )
                source = SourceVersion.objects.create(
                    document=document,
                    filename=filename,
                    kind=kind,
                    byte_size=len(content),
                    sha256=digest,
                )
                job = ExtractionJob.objects.create(source=source)
                source_directory(source).mkdir(parents=True, exist_ok=False)
                saved_path = source_path(source)
                with saved_path.open("xb") as output:
                    output.write(content)
                audit(member.workspace, request.user, "document.uploaded", document)
                transaction.on_commit(lambda: enqueue(str(source.pk), str(job.attempt)))
        except Exception as error:
            if saved_path is not None:
                saved_path.unlink(missing_ok=True)
                saved_path.parent.rmdir()
            if isinstance(error, IntegrityError):
                raise Conflict(
                    "This upload was submitted concurrently. Refresh and retry."
                ) from error
            raise
        document = readable_documents(request.user).get(pk=document.pk)
        return Response(DocumentData(document, context={"request": request}).data, status=201)


class DocumentView(generics.RetrieveAPIView):
    serializer_class = DocumentData
    lookup_url_kwarg = "document_id"

    def get_queryset(self):
        return readable_documents(self.request.user)


class RetryView(APIView):
    @extend_schema(request=RevisionInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to retry extraction.")
        document.refresh_from_db()
        data = validated(RevisionInput, request)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        job = ExtractionJob.objects.select_for_update().get(source__document=document)
        stale = job.state in {
            "QUEUED",
            "EXTRACTING",
        } and job.updated_at < timezone.now() - timedelta(minutes=10)
        if not (job.state == "FAILED" and job.retryable) and not stale:
            raise Conflict(
                "Extraction is active or cannot be retried. Upload a corrected file if needed."
            )
        job.state, job.error, job.retryable, job.attempt = "QUEUED", "", False, uuid.uuid4()
        job.save()
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "document.retried", document)
        transaction.on_commit(lambda: enqueue(str(job.source_id), str(job.attempt)))
        return Response(
            DocumentData(
                readable_documents(request.user).get(pk=document.pk), context={"request": request}
            ).data
        )


class BlockPages(Pages):
    ordering = "position"
    page_size = 100


class BlocksView(generics.ListAPIView):
    serializer_class = BlockData
    pagination_class = BlockPages

    def get_queryset(self):
        source = readable_source(self.request.user, self.kwargs["source_id"])
        blocks = SourceBlock.objects.filter(extraction__source=source)
        page = self.request.query_params.get("page")
        if page:
            if not page.isdigit() or not 1 <= int(page) <= 100:
                raise ValidationError("Choose a valid physical page number.")
            blocks = blocks.filter(locator__page=int(page))
        return blocks


class OriginalView(APIView):
    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, source_id):
        source = readable_source(request.user, source_id)
        try:
            stream = source_path(source).open("rb")
        except FileNotFoundError as error:
            raise NotFound("The original file is unavailable.") from error
        response = FileResponse(
            stream,
            as_attachment=True,
            filename=source.filename,
            content_type="application/octet-stream",
        )
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


class PreviewView(APIView):
    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, source_id, page):
        source = readable_source(request.user, source_id)
        if not hasattr(source, "extraction") or not 1 <= page <= source.extraction.page_count:
            raise NotFound("This source page is unavailable.")
        try:
            stream = (
                source_directory(source) / str(source.extraction.pk) / f"page-{page}.png"
            ).open("rb")
        except FileNotFoundError as error:
            raise NotFound("This source page is unavailable.") from error
        return FileResponse(stream, content_type="image/png")
