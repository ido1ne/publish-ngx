import logging
import os

from django.apps import AppConfig

logger = logging.getLogger("paperless.handlers")


class PaperlessStampConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "paperless_stamp"

    def ready(self):
        PAPERLESS_IDO1NE_INTERNAL_INTERFACE_USER = os.getenv(
            "PAPERLESS_IDO1NE_INTERNAL_INTERFACE_USER",
            "internalInterfaceIdo1ne",
        )
        PAPERLESS_IDO1NE_INTERNAL_INTERFACE_PASSPHRASE = os.environ.get(
            "PAPERLESS_IDO1NE_INTERNAL_INTERFACE_PASSPHRASE",
            "kvHZZ0t$TY&sWCfy7#W",
        )
        # Vérifiez si les migrations ont été appliquées
        logger.debug("INITIALISATION PAPERLESS STAMP OK")


#        if self.check_migrations_applied():
#            # Effectuez vos vérifications ici
#            self.perform_checks()
#
#    def check_migrations_applied(self):
#        # Vérifiez si la base de données est synchronisée avec les migrations
#        try:
#            with connection.cursor() as cursor:
#                cursor.execute("SELECT COUNT(*) FROM django_migrations")
#                migration_count = cursor.fetchone()[0]
#                return migration_count > 0
#        except OperationalError:
#            # La table django_migrations n'existe pas, donc pas de migrations appliquées
#            return False
#
#    def perform_checks(self):
#        # Ajoutez votre logique de vérification ici
#        print("migrations was applied, adding default settings")
