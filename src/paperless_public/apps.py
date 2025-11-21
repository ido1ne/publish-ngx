from django.apps import AppConfig
from paperless import settings

class PaperlessPublicConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paperless_public'

    def ready(self):
        if 'DEFAULT_AUTHENTICATION_CLASSES' in settings.REST_FRAMEWORK:
            settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'].insert(
                0,  # Index 0 to add at the beginning
                'paperless_public.auth.PublicAuthentication'
            )

        print("Paperless Public App is ready and PublicAuthentication added.")
        try:
            user = User.objects.filter(first_name="public").first()
        except user.DoesNotExist:
            CreatePublicUser()


from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from documents.models import User as DocumentUser
from django.db.utils import OperationalError, ProgrammingError

class CreatePublicUser:
    def __init__(self, get_response):
        try:
                # Only run if the Permission table exists (migrations are applied)
                view_uisettings_permission = Permission.objects.get(
                    codename='view_uisettings',
                    content_type__app_label='documents'
                )
                view_document_permission = Permission.objects.get(
                    codename='view_document',
                    content_type__app_label='documents'
                )
                user, created = User.objects.get_or_create(
                    username='public',
                    defaults={
                        'first_name': 'public',
                        'last_name': 'public',
                        'is_active': True,
                    }
                )
                if created:
                    user.user_permissions.add(view_uisettings_permission, view_document_permission)
                    user.save()
        except (OperationalError, ProgrammingError, Permission.DoesNotExist):
            # Database isn't ready or permissions don't exist yet
            pass