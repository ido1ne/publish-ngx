from django.urls import re_path

from paperless_stamp.views import StampWebhookView

urls = [
    re_path("^api/stamp/webhook/$", StampWebhookView.as_view(), name="stamp_webhook"),
]
