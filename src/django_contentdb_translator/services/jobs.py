# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Toolbox job proxy scoped to one sales channel.

Toolbox calls use the instance channel (`AI_TOOLBOX_CHANNEL`); the sales channel lives in job
`metadata.channel_idx`, written at job creation.
"""

from __future__ import annotations

from django_utils_translator.clients import ToolboxClient, ToolboxNotFoundError


def _belongs_to(job: dict, channel_idx: str) -> bool:
    return (job.get("metadata") or {}).get("channel_idx") == channel_idx


def list_jobs(channel_idx: str, status: str | None = None, page: int = 1) -> dict:
    """One toolbox page of jobs, keeping only the jobs created for `channel_idx`.

    No `count`: the toolbox total is instance-wide. `next`/`previous` are toolbox page cursors.
    """
    with ToolboxClient() as client:
        result = client.list_jobs(status=status, page=page)
    jobs = [job for job in result.get("results", []) if _belongs_to(job, channel_idx)]
    return {"results": jobs, "next": result.get("next"), "previous": result.get("previous")}


def get_job(channel_idx: str, job_id: str) -> dict:
    """Job detail; another sales channel's job is reported as not found."""
    with ToolboxClient() as client:
        job = client.get_job(job_id)
    if not _belongs_to(job, channel_idx):
        raise ToolboxNotFoundError("Job not found")
    return job
