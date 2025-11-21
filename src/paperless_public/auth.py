import logging
from django.contrib.auth.models import User

logger = logging.getLogger("paperless.auth")

from rest_framework import authentication
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import User, Permission
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin
from rest_framework import authentication
from rest_framework import exceptions


class PublicAuthentication(BaseAuthentication):
    def authenticate(self, request):
        # Vérifier si l'url contient la partie public de l'api papi, si oui on réécrit l'authentification
        if 'public' in request.path:
            # Récupérer l'utilisateur public
            # test if user public exists, if not create it
            if "public" in [user.username for user in User.objects.all()]:
                user = User.objects.get(username="public")
                return (user, None)
            else:
                try:
                    user, created = User.objects.get_or_create(
                        username="public",
                        first_name="public",
                        last_name="public",
                        defaults={
                            "is_active": True,
                            "is_staff": False,
                        }
                    )
                    if created:
                        view_uisettings_permission = Permission.objects.get(codename='view_uisettings', content_type__app_label='documents')
                        view_document_permission = Permission.objects.get(codename='view_document', content_type__app_label='documents')
                        user.user_permissions.add(view_uisettings_permission, view_document_permission)
                        user.save()
                        logger.info("Created 'public' user automatically.")
                    return (user, None)
                except Exception as e:
                    logger.error(f"Error creating 'public' user: {e}")

