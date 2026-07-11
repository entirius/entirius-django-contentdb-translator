# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Django forms for the translation wizard."""

from django import forms

SCOPE_CHOICES = [
    ("all", "All content of entity type"),
    ("content_type", "By content type"),
    ("single", "Single draft"),
]

ENTITY_TYPE_CHOICES = [
    ("page", "Page"),
    ("navigation", "Navigation"),
    ("author", "Author"),
]

PROVIDER_CHOICES = [
    ("", "Default"),
    ("deepl", "DeepL"),
    ("gemini", "Gemini"),
]


class TranslateConfigForm(forms.Form):
    """Step 1: Translation configuration."""

    channel = forms.ChoiceField(
        label="Channel",
        help_text="Select the channel to translate content for.",
    )
    source_language = forms.ChoiceField(
        label="Source language",
        help_text="Language of the original content.",
    )
    target_languages = forms.MultipleChoiceField(
        label="Target languages",
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more languages to translate into.",
    )
    scope = forms.ChoiceField(
        label="Scope",
        choices=SCOPE_CHOICES,
        widget=forms.RadioSelect,
        initial="all",
        help_text="What content to translate.",
    )
    entity_type = forms.ChoiceField(
        label="Entity type",
        choices=ENTITY_TYPE_CHOICES,
        initial="page",
        help_text="Type of content to translate (for 'all' and 'by content type' scope).",
    )
    content_type_slug = forms.ChoiceField(
        label="Content type",
        required=False,
        help_text="Specific content type to translate (for 'by content type' scope).",
    )
    draft_uid = forms.CharField(
        label="Draft UID",
        required=False,
        help_text="UUID of the specific draft to translate (for 'single draft' scope).",
    )
    force = forms.BooleanField(
        label="Force re-translate",
        required=False,
        initial=False,
        help_text="Overwrite existing translations.",
    )
    publish = forms.BooleanField(
        label="Auto-publish",
        required=False,
        initial=False,
        help_text="Automatically publish translated drafts.",
    )
    provider = forms.ChoiceField(
        label="Provider",
        choices=PROVIDER_CHOICES,
        required=False,
        help_text="Translation provider override.",
    )

    def __init__(self, *args, channels=None, languages=None, content_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        if channels:
            self.fields["channel"].choices = [(c.idx, f"{c.name} ({c.idx})") for c in channels]
        if languages:
            lang_choices = [(lang.iso2, f"{lang.name_en} ({lang.iso2})") for lang in languages]
            self.fields["source_language"].choices = lang_choices
            self.fields["target_languages"].choices = lang_choices
        if content_types:
            ct_choices = [("", "---")] + [(ct.slug, f"{ct.label} ({ct.slug})") for ct in content_types]
            self.fields["content_type_slug"].choices = ct_choices

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")

        if scope == "content_type" and not cleaned.get("content_type_slug"):
            self.add_error("content_type_slug", "Content type is required for 'by content type' scope.")

        if scope == "single" and not cleaned.get("draft_uid"):
            self.add_error("draft_uid", "Draft UID is required for 'single draft' scope.")

        # Remove source language from target languages
        source = cleaned.get("source_language")
        targets = cleaned.get("target_languages", [])
        if source and source in targets:
            cleaned["target_languages"] = [t for t in targets if t != source]
            if not cleaned["target_languages"]:
                self.add_error("target_languages", "Select at least one target language different from the source.")

        return cleaned
