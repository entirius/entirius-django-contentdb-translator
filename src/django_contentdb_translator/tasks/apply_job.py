# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Celery task: poll toolbox for job completion, then apply translations."""

from __future__ import annotations

import logging

from celery import shared_task
from django_utils_translator.clients import ToolboxClient, ToolboxError

from django_contentdb_translator.services.applicator import apply_author_translations, apply_page_translation

logger = logging.getLogger("process")


@shared_task(bind=True, max_retries=120, default_retry_delay=30)
def poll_and_apply_content_job(
    self,
    job_id: str,
    source_draft_id: int | None,
    entity_type: str,
    channel_idx: str,
    target_language: str,
    force: bool = False,
    publish: bool = False,
) -> None:
    """Poll toolbox job status, fetch results on completion, apply translations."""
    with ToolboxClient(channel_idx, max_retries=1) as client:
        try:
            job = client.get_job(job_id)
        except ToolboxError as exc:
            logger.error("Failed to poll content job %s: %s", job_id, exc.message)
            raise self.retry(exc=exc)

        status = job.get("status")
        if status in ("pending", "running"):
            raise self.retry()

        if status == "failed":
            logger.error("Content translation job %s failed: %s", job_id, job.get("error_message", "unknown"))
            return

        if status == "completed":
            _apply_results(client, job_id, source_draft_id, entity_type, channel_idx, target_language, force, publish)


def _apply_results(client, job_id, source_draft_id, entity_type, channel_idx, target_language, force, publish):
    """Fetch all result pages and apply translations."""
    all_results = []
    page = 1
    while True:
        result_page = client.get_job_results(job_id, page=page, page_size=100)
        results = result_page.get("results", [])
        if not results:
            break
        all_results.extend(results)
        if not result_page.get("next"):
            break
        page += 1

    if not all_results:
        logger.warning("Job %s completed with 0 results", job_id)
        return

    if entity_type == "author":
        result = apply_author_translations(items=all_results, target_language=target_language)
        logger.info("Applied %d author translations for job %s", result.updated, job_id)
    else:
        result = apply_page_translation(
            source_draft_id=source_draft_id,
            items=all_results,
            target_language=target_language,
            channel_idx=channel_idx,
            force=force,
            publish=publish,
        )
        logger.info(
            "Applied page translation for job %s → draft_id=%s (%d items)",
            job_id,
            result.created_draft_id,
            result.updated,
        )
