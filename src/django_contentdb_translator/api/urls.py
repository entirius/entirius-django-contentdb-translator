# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import path

from django_contentdb_translator.api.views import BulkJobViewSet, BulkTranslateView, DraftTranslateView

urlpatterns = [
    path(
        "drafts/<str:uid>/translate/", DraftTranslateView.as_view({"post": "create"}), name="contentdb-translate-draft"
    ),
    path("bulk/translate/", BulkTranslateView.as_view({"post": "create"}), name="contentdb-bulk-translate"),
    path("bulk/jobs/", BulkJobViewSet.as_view({"get": "list"}), name="contentdb-bulk-jobs-list"),
    path("bulk/jobs/<str:pk>/", BulkJobViewSet.as_view({"get": "retrieve"}), name="contentdb-bulk-jobs-detail"),
]
