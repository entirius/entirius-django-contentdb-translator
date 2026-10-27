# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`AI_TOOLBOX_ENABLED = False`: the API answers 503 `AI_TOOLBOX_DISABLED`, the apply task returns quietly."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django_utils.toolbox import ToolboxDisabledError, ToolboxNotConfiguredError
from django_utils_translator.clients import ToolboxClient
from rest_framework.test import APIRequestFactory, force_authenticate

from django_contentdb_translator.api.views import BulkJobViewSet, DraftTranslateView
from django_contentdb_translator.tasks.apply_job import poll_and_apply_content_job

JOB = ("job-1", None, "page", "test-shop", "de")
DISABLED = (503, "AI_TOOLBOX_DISABLED")


@pytest.fixture
def configured(settings):
    settings.AI_TOOLBOX_BASE_URL = "https://toolbox.test.internal"
    settings.AI_TOOLBOX_API_KEY = "dummy"
    settings.AI_TOOLBOX_CHANNEL = "test-instance"
    return settings


def _call(view, method: str, body: dict | None = None, **kwargs):
    request = getattr(APIRequestFactory(), method)("/", body, format="json")
    force_authenticate(request, user=get_user_model()(username="admin", is_staff=True))
    response = view(request, shop_idx="test-shop", **kwargs)
    return response.status_code, response.data["error"]


def test_disabled_draft_translate_answers_503(configured):
    view = DraftTranslateView.as_view({"post": "create"})
    body = {"target_languages": ["de"], "dry_run": True}

    with patch("django_contentdb_translator.api.views.translator.translate_draft", side_effect=ToolboxDisabledError()):
        assert _call(view, "post", body, uid="draft-1") == DISABLED


def test_disabled_job_list_answers_503(configured):
    configured.AI_TOOLBOX_ENABLED = False

    assert _call(BulkJobViewSet.as_view({"get": "list"}), "get") == DISABLED


def test_unconfigured_job_list_keeps_its_code(configured):
    configured.AI_TOOLBOX_API_KEY = ""

    assert _call(BulkJobViewSet.as_view({"get": "list"}), "get") == (503, "AI_TOOLBOX_NOT_CONFIGURED")


def test_disabled_apply_task_returns_without_polling(configured, caplog):
    configured.AI_TOOLBOX_ENABLED = False

    with patch.object(ToolboxClient, "get_job") as get_job, caplog.at_level("WARNING", logger="process"):
        assert poll_and_apply_content_job.run(*JOB) is None

    assert not get_job.called
    assert "Translation job job-1 not polled: AI toolbox disabled" in caplog.text


def test_unconfigured_apply_task_still_raises(configured):
    configured.AI_TOOLBOX_API_KEY = ""

    with pytest.raises(ToolboxNotConfiguredError):
        poll_and_apply_content_job.run(*JOB)


def test_configured_apply_task_still_polls(configured):
    with patch.object(ToolboxClient, "get_job", return_value={"status": "failed"}) as get_job:
        assert poll_and_apply_content_job.run(*JOB) is None

    get_job.assert_called_once_with("job-1")
