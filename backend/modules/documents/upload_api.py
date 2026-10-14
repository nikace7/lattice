import hashlib
import os
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api import Conflict
from modules.audit.service import audit
from modules.workspaces.access import (
    can_write,
    locked_collection,
    membership_for,
    readable_collections,
)
from pipeline.source_parser import MAX_BYTES, InvalidSource, validate_bytes

from .access import readable_documents
from .models import (
    Document,
    ExtractionJob,
    SourceVersion,
)
from .serializers import DocumentData, UploadInput
from .storage import source_directory, source_path
from .tasks import enqueue


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
