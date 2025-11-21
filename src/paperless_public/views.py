from django.shortcuts import render
from django.contrib.auth.models import User
from functools import wraps
from documents.views import UnifiedSearchViewSet
from documents.views import UiSettingsView
from documents.views import SavedViewViewSet
from documents.views import StatisticsView
from documents.views import IndexView
from documents.views import SelectionDataView
from documents.views import CustomFieldViewSet
from documents.views import TagViewSet
from documents.views import DocumentViewSet
from documents.models import UiSettings
from documents.serialisers import UiSettingsViewSerializer
from django.views.generic import TemplateView
from django.utils.translation import get_language
from django.conf import settings
from django.contrib.auth import authenticate, login
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
# Python (Django shell or view)
from django.contrib.auth.models import User
from documents.models import UiSettings
from documents.views import SelectionDataView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from documents import bulk_edit
from documents import index
from documents.bulk_download import ArchiveOnlyStrategy
from documents.bulk_download import OriginalAndArchiveStrategy
from documents.bulk_download import OriginalsOnlyStrategy
from documents.caching import get_metadata_cache
from documents.caching import get_suggestion_cache
from documents.caching import refresh_metadata_cache
from documents.caching import refresh_suggestions_cache
from documents.caching import set_metadata_cache
from documents.caching import set_suggestions_cache
from documents.classifier import load_classifier
from documents.conditionals import metadata_etag
from documents.conditionals import metadata_last_modified
from documents.conditionals import preview_etag
from documents.conditionals import preview_last_modified
from documents.conditionals import suggestions_etag
from documents.conditionals import suggestions_last_modified
from documents.conditionals import thumbnail_last_modified
from documents.data_models import ConsumableDocument
from documents.data_models import DocumentMetadataOverrides
from documents.data_models import DocumentSource
from documents.filters import CorrespondentFilterSet
from documents.filters import CustomFieldFilterSet
from documents.filters import DocumentFilterSet
from documents.filters import DocumentsOrderingFilter
from documents.filters import DocumentTypeFilterSet
from documents.filters import ObjectOwnedOrGrantedPermissionsFilter
from documents.filters import ObjectOwnedPermissionsFilter
from documents.filters import PaperlessTaskFilterSet
from documents.filters import ShareLinkFilterSet
from documents.filters import StoragePathFilterSet
from documents.filters import TagFilterSet
from documents.mail import send_email
from documents.matching import match_correspondents
from documents.matching import match_document_types
from documents.matching import match_storage_paths
from documents.matching import match_tags
from documents.models import Correspondent
from documents.models import CustomField
from documents.models import Document
from documents.models import DocumentType
from documents.models import Note
from documents.models import PaperlessTask
from documents.models import SavedView
from documents.models import ShareLink
from documents.models import StoragePath
from documents.models import Tag
from documents.models import UiSettings
from documents.models import Workflow
from documents.models import WorkflowAction
from documents.models import WorkflowTrigger
from documents.parsers import get_parser_class_for_mime_type
from documents.parsers import parse_date_generator
from documents.permissions import PaperlessAdminPermissions
from documents.permissions import PaperlessNotePermissions
from documents.permissions import PaperlessObjectPermissions
from documents.permissions import get_objects_for_user_owner_aware
from documents.permissions import has_perms_owner_aware
from documents.permissions import set_permissions_for_object
from documents.schema import generate_object_with_permissions_schema
from documents.serialisers import AcknowledgeTasksViewSerializer
from documents.serialisers import BulkDownloadSerializer
from documents.serialisers import BulkEditObjectsSerializer
from documents.serialisers import BulkEditSerializer
from documents.serialisers import CorrespondentSerializer
from documents.serialisers import CustomFieldSerializer
from documents.serialisers import DocumentListSerializer
from documents.serialisers import DocumentSerializer
from documents.serialisers import DocumentTypeSerializer
from documents.serialisers import NotesSerializer
from documents.serialisers import PostDocumentSerializer
from documents.serialisers import RunTaskViewSerializer
from documents.serialisers import SavedViewSerializer
from documents.serialisers import SearchResultSerializer
from documents.serialisers import ShareLinkSerializer
from documents.serialisers import StoragePathSerializer
from documents.serialisers import StoragePathTestSerializer
from documents.serialisers import TagSerializer
from documents.serialisers import TagSerializerVersion1
from documents.serialisers import TasksViewSerializer
from documents.serialisers import TrashSerializer
from documents.serialisers import UiSettingsViewSerializer
from documents.serialisers import WorkflowActionSerializer
from documents.serialisers import WorkflowSerializer
from documents.serialisers import WorkflowTriggerSerializer
from documents.serialisers import DocumentListSerializer
from rest_framework import parsers, serializers
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from django.db.models import Count, Case, When, IntegerField

# Create your views here.
def elevate_anonymous_to_read_user(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_anonymous:
            try:
                read_user = User.objects.get(username="public")
                request.user= read_user
                print(f"Elevated to public user: {read_user.username}")
            except User.DoesNotExist:
                pass
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def class_elevate_anonymous_to_read_user(view_func):
    @wraps(view_func)
    def _wrapped_view(self, *args, **kwargs):
        if self.request.user.is_anonymous:
            try:
                read_user = User.objects.get(username="public")
                self.request.user= read_user
                print(f"Elevated to public user: {read_user.username}")
            except User.DoesNotExist:
                pass
        return view_func(self, *args, **kwargs)
    return _wrapped_view



"""
@method_decorator(csrf_exempt, name='dispatch')
class PublicSelectionDataView(SelectionDataView):
    permission_classes = (AllowAny,)  # No permissions required
    @elevate_anonymous_to_read_user
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            try:
                read_user = User.objects.get(username="public")
                request.user= read_user
                print(f"Elevated to public user in SelectionDataView: {read_user.username}")
                return super().dispatch(request, *args, **kwargs)
            except User.DoesNotExist:
                pass
"""


"""
@method_decorator(csrf_exempt, name='dispatch')
class APIPublicSelectionDataView(SelectionDataView):
    permission_classes = (AllowAny,)  # No permissions required
    @class_elevate_anonymous_to_read_user
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

"""

class PublicIndexView(TemplateView):
    template_name="index.html"

    @class_elevate_anonymous_to_read_user
    def get_frontend_language(self):
        if hasattr(
            self.request.user,
            "ui_settings",
        ) and self.request.user.ui_settings.settings.get("language"):
            lang = self.request.user.ui_settings.settings.get("language")
        else:
            lang = get_language()
        # This is here for the following reason:
        # Django identifies languages in the form "en-us"
        # However, angular generates locales as "en-US".
        # this translates between these two forms.
        if "-" in lang:
            first = lang[: lang.index("-")]
            second = lang[lang.index("-") + 1 :]
            return f"{first}-{second.upper()}"
        else:
            return lang

    @class_elevate_anonymous_to_read_user
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cookie_prefix"] = settings.COOKIE_PREFIX
        context["username"] = self.request.user.username
        context["full_name"] = self.request.user.get_full_name()
        context["styles_css"] = f"frontend-public/{self.get_frontend_language()}/styles.css"
        context["runtime_js"] = f"frontend-public/{self.get_frontend_language()}/runtime.js"
        context["polyfills_js"] = (
            f"frontend-public/{self.get_frontend_language()}/polyfills.js"
        )
        context["main_js"] = f"frontend-public/{self.get_frontend_language()}/main.js"
        context["webmanifest"] = (
            f"frontend-public/{self.get_frontend_language()}/manifest.webmanifest"
        )
        context["apple_touch_icon"] = (
            f"frontend-public/{self.get_frontend_language()}/apple-touch-icon.png"
        )
        return context


