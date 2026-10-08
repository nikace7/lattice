import hashlib
import os
import uuid
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied, Throttled, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict, Pages
from modules.workspaces.access import can_write, membership_for, readable_collections
from modules.workspaces.api import audit, locked_collection, validated
from modules.workspaces.serializers import RevisionInput
from pipeline.chunking import VERSION
from pipeline.source_parser import MAX_BYTES, InvalidSource, validate_bytes

from .indexing import RUNNING, configured_profile, enqueue_index
from .models import (
    Chunk,
    Document,
    ExtractionJob,
    ExtractionVersion,
    IndexVersion,
    SourceBlock,
    SourceVersion,
)
from .serializers import BlockData, DocumentData, ReviewInput, UploadInput
from .storage import source_directory, source_path
from .tasks import enqueue


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
    def post(self, request, collection_id=None, document_id=None):
        # Check contribution rights before persisting the source in private storage.
        replacement = (
            get_object_or_404(readable_documents(request.user), pk=document_id)
            if document_id
            else None
        )
        if replacement:
            collection_id = replacement.collection_id
        collection = get_object_or_404(readable_collections(request.user), pk=collection_id)
        if not can_write(collection, membership_for(request.user, collection.workspace_id)):
            raise PermissionDenied("You need contribution access to upload here.")
        raw_data = request.data
        if getattr(request._request, "upload_too_large", False):
            raise ValidationError("The upload exceeds 25 MiB.")
        from .serializers import ReplacementInput

        data = (ReplacementInput if replacement else UploadInput)(data=raw_data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        filename = PurePosixPath(upload.name.replace("\\", "/")).name
        if len(filename) > 200 or upload.size > MAX_BYTES:
            raise ValidationError(
                "Use a filename under 200 characters and a file no larger than 25 MiB."
            )
        suffix = PurePosixPath(filename).suffix.lower()
        kind = {".pdf": "PDF", ".docx": "DOCX", ".txt": "TXT", ".md": "MD"}.get(suffix)
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
                if replacement:
                    replacement = get_object_or_404(
                        readable_documents(request.user), pk=document_id
                    )
                    prior = SourceVersion.objects.filter(pk=data.validated_data["uploadId"]).first()
                    if prior:
                        if (
                            prior.document_id != replacement.pk
                            or (prior.created_by_id or replacement.created_by_id) != request.user.pk
                            or prior.sha256 != digest
                            or prior.filename != filename
                            or prior.ocr_language != data.validated_data["ocrLanguage"]
                        ):
                            raise Conflict(
                                "This replacement identifier already belongs to a different file."
                            )
                        return Response(
                            DocumentData(replacement, context={"request": request}).data
                        )
                    if replacement.revision != data.validated_data["expectedRevision"]:
                        raise Conflict()
                    if (
                        Path(settings.STORAGE_ROOT)
                        / "tombstones"
                        / f"source-{data.validated_data['uploadId']}.json"
                    ).exists():
                        raise Conflict("This replacement identifier belongs to a purged version.")
                existing = Document.objects.filter(pk=data.validated_data["uploadId"]).first()
                if existing and not replacement:
                    original = existing.versions.filter(number=1).first()
                    if (
                        existing.deleted_at is not None
                        or original is None
                        or existing.collection_id != collection.pk
                        or existing.created_by_id != request.user.pk
                        or original.sha256 != digest
                        or original.filename != filename
                        or original.ocr_language != data.validated_data["ocrLanguage"]
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
                    not replacement
                    and Document.objects.filter(
                        collection__workspace=member.workspace, deleted_at__isnull=True
                    ).count()
                    >= member.workspace.document_limit
                ) or total + len(content) > min(
                    settings.MAX_WORKSPACE_STORAGE_BYTES, member.workspace.storage_bytes
                ):
                    raise Throttled(
                        detail="This workspace has reached its document or storage limit."
                    )
                document = replacement or Document.objects.create(
                    id=data.validated_data["uploadId"],
                    collection=collection,
                    title=filename,
                    created_by=request.user,
                )
                source = SourceVersion.objects.create(
                    **(
                        {
                            "id": data.validated_data["uploadId"],
                            "number": document.source.number + 1,
                        }
                        if replacement
                        else {}
                    ),
                    document=document,
                    created_by=request.user,
                    filename=filename,
                    kind=kind,
                    byte_size=len(content),
                    sha256=digest,
                    ocr_language=data.validated_data["ocrLanguage"],
                )
                job = ExtractionJob.objects.create(source=source)
                if replacement:
                    from .lifecycle import cancel_pending

                    cancel_pending(document, except_source=source.pk)
                    document.revision += 1
                    document.save(update_fields=["revision"])
                source_directory(source).mkdir(parents=True, exist_ok=False)
                saved_path = source_path(source)
                with saved_path.open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
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

    def get_object(self):
        document = super().get_object()
        source_id = self.request.query_params.get("sourceId")
        chunk_id = self.request.query_params.get("chunkId")
        try:
            if chunk_id:
                chunk = get_object_or_404(
                    Chunk,
                    pk=uuid.UUID(chunk_id),
                    index__active=True,
                    index__extraction__source__document=document,
                )
                source_id = str(chunk.index.extraction.source_id)
            if source_id:
                document._source = get_object_or_404(
                    document.versions, pk=uuid.UUID(source_id), purge_requested_at__isnull=True
                )
        except ValueError as error:
            raise ValidationError("Choose a valid source or passage.") from error
        return document


class RetryView(APIView):
    @extend_schema(request=RevisionInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to retry extraction.")
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        data = validated(RevisionInput, request)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        job = ExtractionJob.objects.select_for_update().get(source=document.source)
        if not job.can_retry:
            raise Conflict(
                "Extraction is active or cannot be retried. Upload a corrected file if needed."
            )
        job.state, job.error, job.retryable, job.attempt = "QUEUED", "", False, uuid.uuid4()
        job.recoveries = 0
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


class CancelView(APIView):
    @extend_schema(request=RevisionInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to cancel extraction.")
        data = validated(RevisionInput, request)
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        job = ExtractionJob.objects.select_for_update().get(source=document.source)
        if job.state not in {"QUEUED", "EXTRACTING"}:
            raise Conflict("Only queued or extracting documents can be cancelled.")
        job.state, job.error, job.retryable = "CANCELLED", "", False
        job.save(update_fields=["state", "error", "retryable", "updated_at"])
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "document.cancelled", document)
        return Response(
            DocumentData(
                readable_documents(request.user).get(pk=document.pk), context={"request": request}
            ).data
        )


def validate_review_pages(reports, excluded, page_count):
    if len(reports) != page_count or page_count < 1:
        raise ValidationError(
            "This extraction has no complete page report. Upload the source again."
        )
    required = {p["page"] for p in reports if p["status"] in {"FAILED", "EMPTY"}}
    if any(page > page_count for page in excluded) or not required.issubset(excluded):
        raise ValidationError("Exclude every failed or empty page and choose valid page numbers.")


class AcceptReviewView(APIView):
    @extend_schema(request=ReviewInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to accept extraction.")
        data = validated(ReviewInput, request)
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        job = ExtractionJob.objects.select_for_update().get(source=document.source)
        if document.source.kind not in {"PDF", "DOCX"} or job.state != "NEEDS_REVIEW":
            raise Conflict("This extraction is not awaiting review.")
        extraction = ExtractionVersion.objects.select_for_update().get(source=document.source)
        excluded = data["excludedPages"]
        if document.source.kind == "PDF":
            validate_review_pages(extraction.page_reports, excluded, extraction.page_count)
        elif excluded:
            raise ValidationError("Word documents use paragraph references, not page exclusions.")
        if not extraction.blocks.exclude(locator__page__in=excluded).exists():
            raise ValidationError("At least one included page must contain extracted text.")
        extraction.excluded_pages = excluded
        extraction.review_reason = data["reason"]
        extraction.accepted_by = request.user
        extraction.accepted_at = timezone.now()
        extraction.save(
            update_fields=["excluded_pages", "review_reason", "accepted_by", "accepted_at"]
        )
        job.state = "REVIEWED"
        job.save(update_fields=["state", "updated_at"])
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "document.extraction_accepted", document)
        return Response(
            DocumentData(
                readable_documents(request.user).get(pk=document.pk), context={"request": request}
            ).data
        )


class IndexView(APIView):
    @extend_schema(request=RevisionInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to prepare an index.")
        data = validated(RevisionInput, request)
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        if document.source.job.state not in {"EXTRACTED", "REVIEWED"}:
            raise Conflict("Complete extraction and accept any warnings before indexing.")
        extraction = document.source.extraction
        if extraction.warnings and not extraction.accepted_at:
            raise Conflict("Accept extraction warnings before indexing.")
        try:
            profile = member.workspace.index_profile or configured_profile()
        except ValueError as error:
            raise ValidationError(str(error)) from error
        from .models import Reindex

        if Reindex.objects.filter(workspace=member.workspace, state="BUILDING").exists():
            raise Conflict("Wait for the workspace reindex to finish or cancel it first.")
        index = (
            IndexVersion.objects.select_for_update()
            .filter(extraction=extraction, reindex__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if index:
            if not index.can_retry:
                raise Conflict("This index is already ready or still processing.")
            if index.profile != profile or index.chunker != VERSION:
                index = None
        if index:
            index.state, index.error, index.attempt = "QUEUED", "", uuid.uuid4()
            index.recoveries, index.requested_by = 0, request.user
            index.save()
        else:
            index = IndexVersion.objects.create(
                extraction=extraction,
                profile=profile,
                chunker=VERSION,
                requested_by=request.user,
            )
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "document.index_requested", document)
        transaction.on_commit(lambda: enqueue_index(str(index.pk), str(index.attempt)))
        return Response(
            DocumentData(
                readable_documents(request.user).get(pk=document.pk), context={"request": request}
            ).data
        )


class CancelIndexView(APIView):
    @extend_schema(request=RevisionInput, responses=DocumentData)
    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        member, collection = locked_collection(request.user, document.collection_id)
        if not can_write(collection, member):
            raise PermissionDenied("You need contribution access to cancel indexing.")
        data = validated(RevisionInput, request)
        document = get_object_or_404(readable_documents(request.user), pk=document_id)
        if data["expectedRevision"] != document.revision:
            raise Conflict()
        index = get_object_or_404(
            IndexVersion.objects.select_for_update(),
            extraction__source=document.source,
            reindex__isnull=True,
            state__in=RUNNING,
        )
        if index.state not in RUNNING:
            raise Conflict("Only active indexing jobs can be cancelled.")
        index.state, index.error = "CANCELLED", ""
        index.save(update_fields=["state", "error", "updated_at"])
        document.revision += 1
        document.save(update_fields=["revision"])
        audit(member.workspace, request.user, "document.index_cancelled", document)
        return Response(
            DocumentData(
                readable_documents(request.user).get(pk=document.pk), context={"request": request}
            ).data
        )


class BlockPages(Pages):
    ordering = "position"
    page_size = 100


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "chunkId",
                type=uuid.UUID,
                description="Only blocks backing this active source passage.",
            ),
            OpenApiParameter("page", type=int, description="Physical PDF page, from 1 to 100."),
        ]
    )
)
class BlocksView(generics.ListAPIView):
    serializer_class = BlockData
    pagination_class = BlockPages

    def get_queryset(self):
        source = readable_source(self.request.user, self.kwargs["source_id"])
        blocks = SourceBlock.objects.filter(extraction__source=source)
        chunk_id = self.request.query_params.get("chunkId")
        if chunk_id:
            try:
                chunk_id = uuid.UUID(chunk_id)
            except ValueError as error:
                raise ValidationError("Choose a valid passage.") from error
            chunk = get_object_or_404(
                Chunk,
                pk=chunk_id,
                index__extraction__source=source,
                index__active=True,
                index__state="READY",
            )
            blocks = blocks.filter(pk__in=[span["block_id"] for span in chunk.spans])
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
