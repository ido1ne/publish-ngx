from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from documents.views import BulkDownloadView
from documents.views import BulkEditObjectsView
from documents.views import BulkEditView
from documents.views import CorrespondentViewSet
from documents.views import CustomFieldViewSet
from documents.views import DocumentTypeViewSet
from documents.views import GlobalSearchView
from documents.views import IndexView
from documents.views import LogViewSet
from documents.views import PostDocumentView
from documents.views import RemoteVersionView
from documents.views import SavedViewViewSet
from documents.views import SearchAutoCompleteView
from documents.views import SelectionDataView
from documents.views import SharedLinkView
from documents.views import ShareLinkViewSet
from documents.views import StatisticsView
from documents.views import StoragePathViewSet
from documents.views import SystemStatusView
from documents.views import TagViewSet
from documents.views import TasksViewSet
from documents.views import TrashView
from documents.views import UiSettingsView
from documents.views import UnifiedSearchViewSet
from documents.views import WorkflowActionViewSet
from documents.views import WorkflowTriggerViewSet
from documents.views import WorkflowViewSet
from documents.views import serve_logo
from paperless.consumers import StatusConsumer
from paperless.views import ApplicationConfigurationViewSet
from paperless.views import DisconnectSocialAccountView
from paperless.views import FaviconView
from paperless.views import GenerateAuthTokenView
from paperless.views import GroupViewSet
from paperless.views import PaperlessObtainAuthTokenView
from paperless.views import ProfileView
from paperless.views import SocialAccountProvidersView
from paperless.views import TOTPView
from paperless.views import UserViewSet
from paperless_mail.views import MailAccountViewSet
from paperless_mail.views import MailRuleViewSet
from paperless_mail.views import OauthCallbackView
from paperless_mail.views import ProcessedMailViewSet
from rest_framework.routers import DefaultRouter

urlpatterns = [
    re_path(
        "^auth/",
        include(
            ("rest_framework.urls", "rest_framework"),
            namespace="rest_framework",
        ),
    ),
    re_path(
        "^search/",
        include(
            [
                re_path(
                    "^$",
                    GlobalSearchView.as_view(),
                    name="global_search",
                ),
                re_path(
                    "^autocomplete/",
                    SearchAutoCompleteView.as_view(),
                    name="autocomplete",
                ),
            ],
        ),
    ),
    re_path(
        "^statistics/",
        StatisticsView.as_view(),
        name="statistics",
    ),
    re_path(
        "^documents/",
        include(
            [
                re_path(
                    "^post_document/",
                    PostDocumentView.as_view(),
                    name="post_document",
                ),
                re_path(
                    "^bulk_edit/",
                    BulkEditView.as_view(),
                    name="bulk_edit",
                ),
                re_path(
                    "^bulk_download/",
                    BulkDownloadView.as_view(),
                    name="bulk_download",
                ),
                re_path(
                    "^selection_data/",
                    SelectionDataView.as_view(),
                    name="selection_data",
                ),
            ],
        ),
    ),
    re_path(
        "^bulk_edit_objects/",
        BulkEditObjectsView.as_view(),
        name="bulk_edit_objects",
    ),
    re_path(
        "^remote_version/",
        RemoteVersionView.as_view(),
        name="remoteversion",
    ),
    re_path(
        "^ui_settings/",
        UiSettingsView.as_view(),
        name="ui_settings",
    ),
    path(
        "token/",
        PaperlessObtainAuthTokenView.as_view(),
    ),
    re_path(
        "^profile/",
        include(
            [
                re_path(
                    "^$",
                    ProfileView.as_view(),
                    name="profile_view",
                ),
                path(
                    "generate_auth_token/",
                    GenerateAuthTokenView.as_view(),
                ),
                path(
                    "disconnect_social_account/",
                    DisconnectSocialAccountView.as_view(),
                ),
                path(
                    "social_account_providers/",
                    SocialAccountProvidersView.as_view(),
                ),
                path(
                    "totp/",
                    TOTPView.as_view(),
                    name="totp_view",
                ),
            ],
        ),
    ),
    re_path(
        "^status/",
        SystemStatusView.as_view(),
        name="system_status",
    ),
    re_path(
        "^trash/",
        TrashView.as_view(),
        name="trash",
    ),
    re_path(
        r"^oauth/callback/",
        OauthCallbackView.as_view(),
        name="oauth_callback",
    ),
    re_path(
        "^schema/",
        include(
            [
                re_path(
                    "^$",
                    SpectacularAPIView.as_view(),
                    name="schema",
                ),
                re_path(
                    "^view/",
                    SpectacularSwaggerView.as_view(),
                    name="swagger-ui",
                ),
            ],
        ),
    ),
    re_path(
        "^$",  # Redirect to the API swagger view
        RedirectView.as_view(url="schema/view/"),
    ),
]
