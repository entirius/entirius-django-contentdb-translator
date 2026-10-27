# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Toolbox calls use the instance channel; the sales channel lives in job metadata only."""

from unittest.mock import MagicMock, patch

import pytest
from django_utils_translator.clients import ToolboxNotFoundError

from django_contentdb_translator.services import jobs, translator
from django_contentdb_translator.tasks.apply_job import poll_and_apply_content_job

JOBS_CLIENT = "django_contentdb_translator.services.jobs.ToolboxClient"
TRANSLATOR_CLIENT = "django_contentdb_translator.services.translator.ToolboxClient"
TASK = "django_contentdb_translator.tasks.apply_job.poll_and_apply_content_job"
ITEMS = [{"key": "tile.0.text", "text": "Hello"}]


def _job(job_id: str, channel_idx: str | None) -> dict:
    return {"id": job_id, "status": "completed", "metadata": {"channel_idx": channel_idx} if channel_idx else None}


def _draft() -> MagicMock:
    draft = MagicMock(pk=7)
    draft.name = "Home"
    return draft


def test_list_keeps_only_jobs_of_the_sales_channel():
    page = {"count": 3, "results": [_job("own", "shop"), _job("other", "other-shop"), _job("legacy", None)]}

    with patch(JOBS_CLIENT) as MockClient:
        MockClient.return_value.__enter__.return_value.list_jobs.return_value = page
        result = jobs.list_jobs("shop", status="completed", page=2)

    MockClient.assert_called_once_with()
    MockClient.return_value.__enter__.return_value.list_jobs.assert_called_once_with(status="completed", page=2)
    assert [job["id"] for job in result["results"]] == ["own"]
    assert "count" not in result


def test_get_job_of_another_channel_is_not_found():
    with patch(JOBS_CLIENT) as MockClient:
        MockClient.return_value.__enter__.return_value.get_job.return_value = _job("j", "other-shop")

        with pytest.raises(ToolboxNotFoundError):
            jobs.get_job("shop", "j")

    MockClient.assert_called_once_with()


def test_get_own_job_is_returned():
    with patch(JOBS_CLIENT) as MockClient:
        MockClient.return_value.__enter__.return_value.get_job.return_value = _job("j", "shop")

        assert jobs.get_job("shop", "j")["id"] == "j"


def test_draft_jobs_use_instance_channel_and_tag_sales_channel():
    draft = _draft()

    with patch(TRANSLATOR_CLIENT) as MockClient, patch(TASK) as mock_task:
        client = MockClient.return_value.__enter__.return_value
        client.create_job.return_value = {"id": "job-1"}
        translator._dispatch_single_draft(
            "shop", draft, ITEMS, 5, False, ["de"], "pl", [], ["de"], None, None, None, False, False
        )

    MockClient.assert_called_once_with()
    assert client.create_job.call_args.kwargs["metadata"]["channel_idx"] == "shop"
    assert mock_task.delay.call_args.kwargs["channel_idx"] == "shop"


def test_draft_estimate_uses_instance_channel():
    draft = _draft()

    with patch(TRANSLATOR_CLIENT) as MockClient:
        MockClient.return_value.__enter__.return_value.estimate.return_value = {"per_language": []}
        translator._estimate_single_draft(draft, ITEMS, 5, ["de"], [], ["de"], None)

    MockClient.assert_called_once_with()


def test_poll_uses_instance_channel():
    with patch("django_contentdb_translator.tasks.apply_job.ToolboxClient") as MockClient:
        MockClient.return_value.get_job.return_value = {"status": "failed"}
        poll_and_apply_content_job.run("job-1", None, "page", "shop", "de")

    MockClient.assert_called_once_with(max_retries=1)


def test_poll_gives_up_when_job_not_found():
    with patch("django_contentdb_translator.tasks.apply_job.ToolboxClient") as MockClient:
        MockClient.return_value.__enter__.return_value.get_job.side_effect = ToolboxNotFoundError("Job not found")
        with patch.object(poll_and_apply_content_job, "retry") as mock_retry:
            poll_and_apply_content_job.run("job-1", None, "page", "shop", "de")

    mock_retry.assert_not_called()
