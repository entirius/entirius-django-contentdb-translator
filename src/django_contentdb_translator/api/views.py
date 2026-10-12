# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""DRF views for django-contentdb-translator.

Auth: JWT + IsAdminUser. Outbound calls to toolbox via ToolboxClient.
"""

from __future__ import annotations

import logging
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from django_utils_translator.clients import ToolboxClient, ToolboxError
from django_utils_translator.views import handle_toolbox_error
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_contentdb_translator.schemas.requests import BulkTranslateRequest, TranslateDraftRequest
from django_contentdb_translator.services import translator

logger = logging.getLogger("process")


def _internal_error_response(exc: Exception) -> Response:
    """Log the exception with a random error_id and return a safe 500."""
    error_id = uuid.uuid4().hex[:8]
    logger.exception("Internal error [%s]", error_id)
    return Response(
        {"error": "INTERNAL_ERROR", "message": f"Internal server error [{error_id}]"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


_CHANNEL_PARAM = OpenApiParameter(
    name="shop_idx", location="path", description="Channel identifier", required=True, type=str
)


@extend_schema_view(
    create=extend_schema(
        tags=["Content Translations"],
        summary="Translate draft",
        description="Translate a single draft to target languages. dry_run=true for cost estimate.",
        parameters=[_CHANNEL_PARAM],
        request=TranslateDraftRequest,
        responses={
            200: {"description": "Dry-run estimate"},
            202: {"description": "Jobs created"},
            400: {"description": "Validation error"},
        },
    ),
)
class DraftTranslateView(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "contentdb_translator.translate"

    def create(self, request: Request, shop_idx: str, uid: str) -> Response:
        try:
            data = TranslateDraftRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            result = translator.translate_draft(
                channel_idx=shop_idx,
                draft_uid=uid,
                target_languages=data.target_languages,
                source_language=data.source_language,
                provider=data.provider,
                formality=data.formality,
                context=data.context,
                dry_run=data.dry_run,
                force=data.force,
                publish=data.publish,
            )
        except ValueError as exc:
            return Response({"error": "VALIDATION_ERROR", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ObjectDoesNotExist:
            return Response(
                {"error": "NOT_FOUND", "message": f"Draft '{uid}' not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except ToolboxError as exc:
            return handle_toolbox_error(exc)
        except Exception as exc:
            return _internal_error_response(exc)

        http_status = status.HTTP_200_OK if data.dry_run else status.HTTP_202_ACCEPTED
        return Response(result.model_dump(), status=http_status)


@extend_schema_view(
    create=extend_schema(
        tags=["Content Translations"],
        summary="Bulk translate content",
        description="Translate all content of a type (page/navigation/author) in a channel. dry_run=true for estimate.",
        parameters=[_CHANNEL_PARAM],
        request=BulkTranslateRequest,
        responses={
            200: {"description": "Estimate"},
            202: {"description": "Jobs created"},
            400: {"description": "Validation error"},
        },
    ),
)
class BulkTranslateView(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "contentdb_translator.translate"

    def create(self, request: Request, shop_idx: str) -> Response:
        try:
            data = BulkTranslateRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            result = translator.translate_bulk(
                channel_idx=shop_idx,
                entity_type=data.entity_type,
                target_languages=data.target_languages,
                source_language=data.source_language,
                provider=data.provider,
                formality=data.formality,
                context=data.context,
                dry_run=data.dry_run,
                force=data.force,
                publish=data.publish,
                content_type_slug=data.content_type_slug,
            )
        except ValueError as exc:
            return Response({"error": "VALIDATION_ERROR", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ObjectDoesNotExist as exc:
            return Response({"error": "NOT_FOUND", "message": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)
        except Exception as exc:
            return _internal_error_response(exc)

        http_status = status.HTTP_200_OK if data.dry_run else status.HTTP_202_ACCEPTED
        return Response(result.model_dump(), status=http_status)


@extend_schema_view(
    list=extend_schema(
        tags=["Content Translation Jobs"],
        summary="List translation jobs",
        parameters=[_CHANNEL_PARAM],
        responses={200: {"description": "Job list from toolbox"}},
    ),
    retrieve=extend_schema(
        tags=["Content Translation Jobs"],
        summary="Get job detail",
        parameters=[_CHANNEL_PARAM],
        responses={200: {"description": "Job detail"}, 404: {"description": "Not found"}},
    ),
)
class BulkJobViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "contentdb_translator.translate"

    def list(self, request: Request, shop_idx: str) -> Response:
        status_filter = request.query_params.get("status")
        try:
            page = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            return Response(
                {"error": "VALIDATION_ERROR", "message": "page must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            with ToolboxClient(shop_idx) as client:
                result = client.list_jobs(status=status_filter, page=page)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)
        return Response(result, status=status.HTTP_200_OK)

    def retrieve(self, request: Request, shop_idx: str, pk: str | None = None) -> Response:
        try:
            with ToolboxClient(shop_idx) as client:
                result = client.get_job(pk)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)
        return Response(result, status=status.HTTP_200_OK)
