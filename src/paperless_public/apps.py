from django.apps import AppConfig
from paperless import settings
import logging

logger = logging.getLogger("paperless_public")
file_handler = logging.FileHandler(settings.LOGGING_DIR / "paperless_public.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

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

@staticmethod
def checkAndSetLogoFolder():
    try:
        MEDIA_ROOT = settings.MEDIA_ROOT
        LOGO_DIR = MEDIA_ROOT / "logo"
        logger.debug(f"Check Logo dir {LOGO_DIR} exists")
        if not LOGO_DIR.exists():
            LOGO_DIR.mkdir(parents=True)
    except:
        raise Exception(f"Failed to initialize LOGO dir {LOGO_DIR} ")