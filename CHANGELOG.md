# Changelog

## [Unreleased]

- Access: the module declares its own access areas on its AppConfig and its admin views (copied from the
  entirius-django-access defaults; behaviour unchanged).

## 2.0.1 — 2026-07-11

- Add the missing proxy-model migration for the admin translate wizard.

## 2.0.0 — 2026-07-11

- Initial public release: AI translation bridge for ContentDB — extracts
  translatable text from Content JSON (tiles, meta, extensions, navigation,
  routes, authors), sends it to the AI Toolbox, and clones Drafts with
  translated content. Zero local models; the toolbox owns jobs, costs, and
  usage.
- Admin API v2: single-draft and bulk translation with `dry_run` cost
  estimation, job listing and status proxied from the toolbox.
- `translate_content` management command for CLI bulk translation.
