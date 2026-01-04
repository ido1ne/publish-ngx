import io
import json
import logging
import os
import time

import requests
from celery import chain
from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import Permission

# from pyhanko.sign.timestamps.aiohttp_client import AIOHttpTimeStamper
# from pyhanko_certvalidator.fetchers.aiohttp_fetchers import AIOHttpFetcherBackend
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pyhanko import stamp
from pyhanko.pdf_utils import text
from pyhanko.pdf_utils.font import opentype

# import aiohttp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields
from pyhanko.sign import signers
from pyhanko.sign.fields import SigSeedSubFilter

from paperless import settings
from paperless.celery import app

logger = logging.getLogger("paperless.handlers")


@csrf_exempt  # This is to disable CSRF validation for the incoming POST requests
def webhook(request):
    if request.method == "POST" and "webhook" in request.path and CreateInterfaceUser():
        try:
            logger.debug("Webook detecting : updating in progress")
            doc_url = request.POST.get("doc_url")

            if doc_url:
                logger.debug("Fetching PDF from URL: %s", doc_url)
                doc_id = doc_url.strip("/").split("/")[-1]
                logger.debug("Extracted doc ID: %s", doc_id)
                document = Documents(doc_id=doc_id)

                # Download document to test if signature already exists
                Documents.download_file_pdf(doc_id)
                logger.debug(
                    "Tests if document is already publishing by testing signature presence",
                )

                if not SignAndStampDocument.check_already_signed(doc_id):
                    logger.debug("not ever signed, published")
                    ##task=process_document_task.delay(doc_id, api_client)
                    mytaskstate = Statetask()
                    #   ### Enchaine les taches et envoi le resultat à la suivante si la tâche est SUCCESS
                    #   ##result = process_document_task.apply_async(args=(doc_id, api_client), link=get_stat_of_task.s())
                    result = chain(
                        document.process_document_task.s(document),
                        mytaskstate.get_stat_of_task.s(previous_doc=document),
                        mytaskstate.post_send_signed_doc.s(previous_doc=document),
                        ##get_stat_of_task.s()  # assuming it's a fixed argument
                    )()
                    # document.modify_shared_link(document.shared_link_id)

                else:
                    logger.debug("!!! Already sign !!!")
                return JsonResponse({"message": "PDF received and tested."}, status=200)

        except Exception as e:
            logger.exception("Error handling webhook: %s", e)
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method."}, status=405)


class APIClient:
    def __init__(self):
        self.base_url = "http://localhost:8000/api"
        # self.username="admin"
        # self.password="adminadmin"
        self.username = os.getenv(
            "PAPERLESS_IDO1NE_INTERNAL_INTERFACE_USER",
            "internalInterfaceIdo1ne",
        )
        self.password = os.getenv(
            "PAPERLESS_IDO1NE_INTERNAL_INTERFACE_PASSPHRASE",
            "kvHZZ0t$TY&sWCfy7#W",
        )
        logger.debug(f"APIClient init with user {self.username} and {self.password}")

        self.token = self.retrieve_token()
        self.headers = self.retrieve_headers()

    def retrieve_headers(self):
        return {"Authorization": f"Token {self.token}"}

    def retrieve_token(self):
        response = requests.post(
            f"{self.base_url}/token/",
            data={"username": self.username, "password": self.password},
        )
        if response.status_code == 200:
            token_data = response.json()
            # app.logger.info("Token retrieved successfully %s", token_data)
            return token_data.get("token")
        else:
            raise Exception("Failed to retrieve token")

    def get_task_status(self, uuidtask):
        # /api/tasks/?task_id={uuid}
        url = self.base_url + "/tasks/?task_id=" + uuidtask
        response = requests.get(url, headers=self.headers)
        return self._handle_response(response)

    def get(self, endpoint):
        url = self.base_url + "/" + endpoint
        response = requests.get(url, headers=self.headers)
        # print(response.content)
        return self._handle_response(response)

    def post_document(self, endpoint, data, files):
        url = self.base_url + "/" + endpoint
        response = requests.post(url, headers=self.headers, data=data, files=files)
        logger.debug("POST %s response: %s", url, response.content)
        return self._handle_response(response)

    def patch_right(self, endpoint, data):
        url = self.base_url + "/" + endpoint
        response = requests.patch(url, headers=self.headers, data=data)
        logger.debug("POST %s response: %s", url, response.content)
        return self._handle_response(response)

    def generate_sharing_link(self, endpoint, data):
        url = self.base_url + "/" + endpoint
        response = requests.post(url, headers=self.headers, data=data)
        logger.debug("POST %s response: %s", url, response.content)
        return self._handle_response(response)

    def patch_shared_link(self, endpoint, data):
        url = self.base_url + "/" + endpoint
        response = requests.patch(url, headers=self.headers, data=data)
        logger.debug("POST %s response: %s", url, response.content)
        return self._handle_response(response)

    def post(self, endpoint, data):
        url = self.base_url + "/" + endpoint
        response = requests.post(url, headers=self.headers, data=data)
        logger.debug("POST %s response: %s", url, response.content)
        return self._handle_response(response)

    def delete(self, endpoint):
        url = self.base_url + "/" + endpoint
        response = requests.delete(url, headers=self.headers)
        return self._handle_delete_response(response)

    def _handle_response(self, response):
        if response.status_code == 200 or response.status_code == 201:
            return response
        else:
            response.raise_for_status()

    def _handle_delete_response(self, response):
        if response.status_code == 204:
            return response
        else:
            response.raise_for_status()


class Documents:
    def __init__(self, *args, **kwargs):
        self.api_client = APIClient()
        logger.debug("Initializing Documents with args: %s, kwargs: %s", args, kwargs)
        self.doc_id = kwargs.get("doc_id")
        # self.cf_date_de_debut_de_publication = "2020-11-23"
        # self.cf_date_de_fin_de_publication = "2020-11-26"
        # self.cf_annexes_a_publier = [43,42]  # Example IDs for annexes to publish
        self.shared_link_id = ""

        if self.checkfolder():
            MEDIA_ROOT = settings.MEDIA_ROOT
            STAMPS_DIR = MEDIA_ROOT / "stamps"
            self.STAMPS_DIR = STAMPS_DIR

    @staticmethod
    def checkfolder():
        try:
            MEDIA_ROOT = settings.MEDIA_ROOT
            STAMPS_DIR = MEDIA_ROOT / "stamps"
            CERTS_DIR = MEDIA_ROOT / "certs"

            logger.debug("Ensuring stamps directory exists at: %s", STAMPS_DIR)
            if not STAMPS_DIR.exists():
                STAMPS_DIR.mkdir(parents=True)
            if not CERTS_DIR.exists():
                CERTS_DIR.mkdir(parents=True)
            return True
        except:
            raise Exception(f"Failed to initialize Stamp dir {STAMPS_DIR}")
            return False

    @shared_task
    def process_document_task(self):
        # api_client = APIClient()
        sign_client = SignAndStampDocument()
        self.load_from_api()
        self.save_original_metadata_by_api()
        self.load_original_metadata_from_file()
        self.download_pdf()
        self.display_document_json_data()
        logger.debug("Test if document could be signed")
        sign_client.applySignature(
            f"{self.STAMPS_DIR}/{self.doc_id}.pdf",
            f"{self.STAMPS_DIR}/{self.doc_id}_sign.pdf",
        )
        logger.debug("Document %s was SIGNED successfully.", self.doc_id)
        last_id = self.get_last_id_of_document()
        logger.debug(f"Create a sharing link on {last_id}")
        self.make_a_sharing_link(last_id)
        self.delete_original_document()
        self.empty_original_document_from_trash()
        uuidtask = self.post_new_document(f"{self.STAMPS_DIR}/{self.doc_id}_sign.pdf")
        logger.debug(
            "Document %s was SIGNED and posted with UUID: %s",
            self.doc_id,
            uuidtask,
        )
        return uuidtask

    def load_from_api(self):
        if self.doc_id:
            data = self.api_client.get(
                "documents/" + self.doc_id + "/" + "?full_perms=true",
            ).json()
            self.doc_id = str(data.get("id"))
            return Documents
        else:
            raise Exception(f"Failed to load document with id {self.doc_id}")

    def save_original_metadata_by_api(self):
        # doc_url="http://localhost:8000/api/documents/"+self.doc_id+"/"
        if self.doc_id:
            data = self.api_client.get("documents/" + self.doc_id + "/")
            # write metadata to file
            open(f"{self.STAMPS_DIR}/{self.doc_id}_metadata.json", "w").write(data.text)
        else:
            raise Exception(f"Failed to load document with id {self.doc_id}")

    def load_original_metadata_from_file(self):
        if self.doc_id:
            data = open(f"{self.STAMPS_DIR}/{self.doc_id}_metadata.json").read()
            datajson = json.loads(data)

            # Modify owner to public user
            datajson["owner"] = self.get_id_of_public_user()
            # datajson['set_permissions']={
            #    "view": {
            #        "users": [],
            #        "groups": [self.get_id_of_public_group()],
            #    },
            #    "change": {
            #        "users": [],
            #        "groups": [],
            #    },
            # }
            # Modify custom fields
            custom_fields = datajson.get("custom_fields", [])
            # Detect number of custom fields
            counter_of_custom_fields = len(custom_fields)

            for field in custom_fields:
                if (
                    field.get("field") == 1
                ):  # Assuming field ID 1 is for 'date_de_debut_de_publication'
                    self.cf_date_de_debut_de_publication = field.get("value")
                elif (
                    field.get("field") == 2
                ):  # Assuming field ID 2 is for 'date_de_fin_de_publication'
                    self.cf_date_de_fin_de_publication = field.get("value")
                elif (
                    field.get("field") == 3
                ):  # Assuming field ID 3 is for 'annexes_a_publier'
                    self.cf_annexes_a_publier = field.get("value")

            # Example: set custom field with ID 1 to "2025-11-23" and ID 2 to "2025-11-26" and ID 3 to [43,42]
            # {"1": "2025-11-23","2": "2025-11-26","3":[43,42]}

            # del datajson['custom_fields']
            custom_fields = {
                "1": self.cf_date_de_debut_de_publication,
                "2": self.cf_date_de_fin_de_publication,
                "3": self.cf_annexes_a_publier,
            }
            datajson["custom_fields"] = json.dumps(custom_fields)
            # datajson['custom_fields'] = '{\'1\': \'' + self.cf_date_de_debut_de_publication + '\', \'2\': \'' + self.cf_date_de_fin_de_publication + '\', \'3\': [' + ', '.join(map(str, self.cf_annexes_a_publier)) + ']}'
            # write data json to file
            open(f"{self.STAMPS_DIR}/{self.doc_id}_metadata_modified.json", "w").write(
                json.dumps(datajson),
            )
            # logger.debug("Document JSON Data: %s", json.dumps(datajson, indent=4))

            # Example to read existing custom fields
            # existing_custom_fields=

            # data_maj=json.dumps(data)
            # write metadata to file
            # open(f"{STAMPS_DIR}/{self.doc_id}_metadata.json", "w").write(data_maj)
            return Documents
        else:
            raise Exception(f"Failed to load document with id {self.doc_id} from file")

    @staticmethod
    def get_id_of_public_group():
        api_client = APIClient()
        data = api_client.get("groups/?name__iexact=_public").json()
        if data:
            group_id = data["results"][0]["id"]
            return group_id

    @staticmethod
    def get_id_of_public_user():
        api_client = APIClient()
        data = api_client.get("users/?username__iexact=public").json()
        if data:
            user_id = data["results"][0]["id"]
            logger.debug(f"public user id {user_id}")
            return user_id

    def download_pdf(self):
        if self.doc_id:
            pdf = self.api_client.get("documents/" + self.doc_id + "/download/")
            open(f"{self.STAMPS_DIR}/{self.doc_id}.pdf", "wb").write(pdf.content)
            return f"Document {self.doc_id} downloaded successfully."
        else:
            raise Exception(f"Failed to download document with id {self.doc_id}")

    @staticmethod
    def download_file_pdf(doc_id):
        MEDIA_ROOT = settings.MEDIA_ROOT
        STAMPS_DIR = MEDIA_ROOT / "stamps"
        if doc_id:
            api_client = APIClient()
            pdf = api_client.get("documents/" + doc_id + "/download/")
            open(f"{STAMPS_DIR}/{doc_id}.pdf", "wb").write(pdf.content)
            return f"Document {doc_id} downloaded successfully."
        else:
            raise Exception(f"Failed to download document with id {doc_id}")

    def display_document_json_data(self):
        if self.doc_id:
            data = open(f"{self.STAMPS_DIR}/{self.doc_id}_metadata.json").read()
            data = json.loads(data)

            logger.debug("Document JSON Data: %s", json.dumps(data, indent=4))
        else:
            raise Exception(f"Failed to load document with id {self.doc_id} from file")

    def stamp_document(self):
        # Create a PDF stamp with the custom field information
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        can.drawString(
            100,
            750,
            f"Date de debut de publication: {self.cf_date_de_debut_de_publication}",
        )
        can.drawString(
            100,
            730,
            f"Date de fin de publication: {self.cf_date_de_fin_de_publication}",
        )
        can.save()

        # Move to the beginning of the StringIO buffer
        packet.seek(0)
        stamp_pdf = PdfReader(packet)

        # Read the existing PDF
        existing_pdf = PdfReader(open(f"{self.doc_id}.pdf", "rb"))
        output = PdfWriter()

        # Add the stamp to each page
        for page_num in range(len(existing_pdf.pages)):
            page = existing_pdf.pages[page_num]
            page.merge_page(stamp_pdf.pages[0])
            output.add_page(page)

        # Save the stamped PDF
        with open(f"{self.doc_id}_stamped.pdf", "wb") as outputStream:
            output.write(outputStream)

        print(f"Document {self.doc_id} stamped successfully.")

    def delete_original_document(self):
        if self.doc_id:
            response = self.api_client.delete("documents/" + self.doc_id + "/")
            print(f"Document {self.doc_id} deleted successfully.")
        else:
            raise Exception(f"Failed to delete document with id {self.doc_id}")

    def empty_original_document_from_trash(self):
        if self.doc_id:
            data = {
                "documents": [int(self.doc_id)],
                "action": "empty",
            }
            self.api_client.post("trash/", data=data)
            print(f"Document {self.doc_id} emptied from trash successfully.")

    def simple_post_new_document(self):
        MEDIA_ROOT = settings.MEDIA_ROOT

        STAMPS_DIR = MEDIA_ROOT / "stamps"
        logger.debug("Ensuring stamps directory exists at: %s", STAMPS_DIR)
        if not STAMPS_DIR.exists():
            STAMPS_DIR.mkdir(parents=True)

        if os.path.exists(f"{STAMPS_DIR}/{self.doc_id}.pdf"):
            files = {"document": open(f"{STAMPS_DIR}/{self.doc_id}.pdf", "rb")}
            data = {
                "title": "test12",  # Simplified title
            }
            response = self.api_client.post_document(
                endpoint="documents/post_document/",
                data=data,
                files=files,
            )
        else:
            raise Exception(f"Failed to post new document {self.doc_id}")

    def make_a_sharing_link(self, doc_id):
        if self.doc_id:
            # convert dates de fin de publication in format 2025-12-30T10:14:09.538Z
            date_fin_publication = self.cf_date_de_fin_de_publication + "T00:00:01.538Z"
            # data = "expiration": "{date_fin_publication}", "document": {self.doc_id}, "file_version": "original"}}'
            data = {
                "expiration": date_fin_publication,
                "document": doc_id,
                "file_version": "original",
            }
            logger.debug(f"data sent to make shared link:{data}")
            response = self.api_client.generate_sharing_link(
                "share_links/",
                data,
            ).json()
            self.shared_link_id = response.get("id")
            logger.debug(f"--- Shared link ID is : {self.shared_link_id}")
        else:
            raise Exception(
                f"Failed to make a sharink link for the document {self.doc_id}",
            )

    def modify_shared_link(self, shared_link_id):
        if self.doc_id:
            data = {"document": self.doc_id}
            response = self.api_client.patch_shared_link(
                f"share_links/{shared_link_id}/",
                data,
            ).json()
            result = response.get("id")
            logger.debug(f" Result of patched shared link ID is : {result}")
        else:
            raise Exception(
                f"Failed to make a sharink link for the new document : {response}",
            )

    def post_new_document(self, signed_doc_path):
        test_file_path = f"STAMPS_DIR{self.doc_id}.pdf"
        metadata_file_path = f"STAMPS_DIR{self.doc_id}_metadata_modified.json"
        if os.path.exists(f"{self.STAMPS_DIR}/{self.doc_id}_sign.pdf"):
            files = {"document": open(f"{signed_doc_path}", "rb")}
            data = open(
                f"{self.STAMPS_DIR}/{self.doc_id}_metadata_modified.json",
            ).read()
            data = json.loads(data)
            # custom fields must be like {"1": "2025-11-23","2": "2025-11-26","3":[43,42]}

            response = self.api_client.post_document(
                endpoint="documents/post_document/",
                data=data,
                files=files,
            )
            if response.status_code == 200:
                response_data = response.json()
                # return response data content
                return response_data
            else:
                raise Exception(
                    f"Failed to post new document {self.doc_id}, status code: {response.status_code}",
                )
        else:
            raise Exception(f"Failed to post new document {self.doc_id}")

    def get_status_of_task(self, uuidtask):
        status = "PENDING"
        related_document = None
        timeout_duration = 60  # Duration limit for waiting (in seconds)
        start_time = time.time()

        # Loop until the task status is SUCCESS or timeout occurs
        logger.debug("Waiting for task %s to complete...", uuidtask)
        while True:
            try:
                response = self.api_client.get_task_status(uuidtask)
                data = response.json()
                logger.debug(
                    "Task status response data: %s",
                    json.dumps(data, indent=4),
                )

                if data and isinstance(data, list) and len(data) > 0:
                    status = data[0]["status"]
                    related_document = data[0].get("related_document")

                    logger.debug("Current task status: %s", status)

                    if status == "SUCCESS":
                        logger.info("Task %s completed successfully.", uuidtask)
                        break
                    elif status in ["FAILURE", "REVOKED"]:
                        logger.error("Task %s failed or was revoked.", uuidtask)
                        return None  # ou lève une exception ou retourne un message approprié

            except Exception as e:
                logger.error("Error while getting task status: %s", str(e))
                return None  # ou lève une exception ou retourne un message approprié

            # Check if the waiting time has exceeded the limit
            if time.time() - start_time > timeout_duration:
                logger.error(
                    "Timeout: Unable to retrieve SUCCESS status for task %s",
                    uuidtask,
                )
                return None  # ou lève une exception ou retourne un message approprié
            time.sleep(2)  # Wait before checking again
        # If we reach here, the task has completed successfully
        logger.debug(
            "Task %s completed with related document: %s",
            uuidtask,
            related_document,
        )
        # Now we can return the related document ID or any other relevant information
        if related_document:
            logger.debug("Related document ID: %s", related_document)
            return related_document
        else:
            logger.warning("No related document found for task %s", uuidtask)
        # Wait for the task to complete and return the related document
        logger.debug("Waiting for task %s to complete...", uuidtask)
        start_time = time.time()
        status = "PENDING"
        related_document = None
        # Loop until the task status is SUCCESS or timeout occurs
        logger.debug("Waiting for task %s to complete...", uuidtask)

    def set_new_right(self):
        # data= {
        #    "owner": self.get_id_of_public_user(),
        #    "set_permissions": {
        #        "view": {
        #            "users": [],
        #            "groups": [self.get_id_of_public_group()],
        #        },
        #        "change": {
        #            "users": [],
        #            "groups": [],
        #        },
        #    },
        # }
        public_user_id = self.get_id_of_public_user()
        data = {"owner": public_user_id}
        response = self.api_client.patch_right(
            endpoint="documents/" + self.doc_id + "/",
            data=data,
        ).json()
        if response.get("owner") == public_user_id:
            logger.debug(f"set new rights with public user ({public_user_id})")

    def get_last_id_of_document(self):
        # dernier document publié
        owner = self.get_id_of_public_group()
        response = self.api_client.get(
            f"documents/?ordering=-id&owner__id={owner}",
        ).json()
        if response.get("results"):
            last_doc_id = response["results"][0]["id"]
            return last_doc_id


class Statetask:
    def __init__(self, *args, **kwargs):
        logger.debug("Initializing Statetask with args: %s, kwargs: %s", args, kwargs)

    @app.task
    def get_stat_of_task(uuid, previous_doc):
        api_client = APIClient()
        # logger.debug(f"task to check{uuid}")
        response = api_client.get_task_status(uuidtask=uuid)
        data = response.json()
        related_document = data[0].get("related_document")
        # logger.debug("Task JSON Data: %s", json.dumps(data, indent=4))
        logger.debug(f" Related document is : {related_document}")
        time.sleep(5)
        logger.debug("RETRIERVE NEW TWO TASK")
        logger.debug(f"PREVIOUS DOC HAS {previous_doc.doc_id}")
        return related_document
        # document.set_new_right(doc_id=related_document)
        # test=SignAndStampDocument()
        # test.applySignature()

    @app.task
    def post_send_signed_doc(related_document, previous_doc):
        try:
            newdoc = Documents(doc_id=related_document)
            newdoc.set_new_right()
            newdoc.modify_shared_link(shared_link_id=previous_doc.shared_link_id)
            # TO DO
            # patch shared link

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
        # api_client = APIClient()
        # Change document with public rights
        # ndocument = Documents(doc_id=str(related_document), api_client=api_client)
        # id_public_user = ndocument.get_id_of_public_group()
        # id_public_group = ndocument.get_id_of_public_user()
        # logger.debug(f"Set new rights for {related_document} with {id_public_user} and {id_public_group}")


def CreateInterfaceUser():
    logger.debug("try to create internalInterface user")
    if User.objects.filter(first_name="internalInterfaceIdo1ne").exists():
        return True
    else:
        try:
            # Only run if the Permission table exists (migrations are applied)
            view_uisettings_permission = Permission.objects.get(
                codename="view_uisettings",
                content_type__app_label="documents",
            )
            view_document_permission = Permission.objects.get(
                codename="view_document",
                content_type__app_label="documents",
            )
            user, created = User.objects.get_or_create(
                username="internalInterfaceIdo1ne",
                defaults={
                    "first_name": "internalInterfaceIdo1ne",
                    "last_name": "internalInterfaceIdo1ne",
                    "password": "kvHZZ0t$TY&sWCfy7#W",
                    "is_active": True,
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            if created:
                user.user_permissions.add(
                    view_uisettings_permission,
                    view_document_permission,
                )
                user.save()
            logger.debug("create internalInterface user successfully")
            return True
        except:
            logger.debug("Failed to create internalInterface user")
            return False


# @app.task
# def get_stat_of_task(self):
#    logger.debug(f"NEW TASK THAT I WANT TO CHECK {self.uuid}")
#    time.sleep(5)
#    logger.debug(f"RETRIERVE NEW TWO TASK")


class SignAndStampDocument:
    def __init__(self):
        try:
            MEDIA_ROOT = settings.MEDIA_ROOT  # Ensure MEDIA_ROOT is a Path object
            CERTS_DIR = MEDIA_ROOT / "certs"
            if not CERTS_DIR.exists():
                CERTS_DIR.mkdir(parents=True)

            self.CERTS_DIR = str(CERTS_DIR)

            # certificate in p12 format
            self.CERT_PATH_FILE_P12 = self.CERTS_DIR + "/cert.p12"
            self.CERT_PASSPHRASE_P12 = b"l1O!Yutd@XTceY2D"
            # certificate in pem format
            self.CERT_PATH_FILE = self.CERTS_DIR + "/domain.crt"
            self.CERT_KEY_FILE = self.CERTS_DIR + "/domain.key"
            self.CERT_PASSPHRASE = b"PASSPHRASE"

            logger.debug(f"certs dir is: {self.CERT_PATH_FILE}")

            self.STAMP_FONT = self.CERTS_DIR + "/NotoSans-Regular.ttf"
            self.TRUST_CA_CERT = self.CERTS_DIR + "/chain.cer"
            # self.infile='/usr/src/paperless/paperless-ngx/media/stamps/17.pdf'
            # self.outfile='/usr/src/paperless/paperless-ngx/media/stamps/17sign.pdf'
            logger.debug(f"{self.CERT_PATH_FILE}")
            # self.createSignerpkcsp12()
            self.createSignerpkcs()
            self.signatureMeta()
        except:
            raise Exception(f"Failed to initialize Stamp dir {self.CERTS_DIR}")

    # récupération des infos du certificate
    def createSignerpkcsp12(self):
        self.signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=self.CERT_PATH_FILE_P12,
            passphrase=self.CERT_PASSPHRASE_P12,
        )

    def createSignerpkcs(self):
        self.signer = signers.SimpleSigner.load(
            cert_file=self.CERT_PATH_FILE,
            key_file=self.CERT_KEY_FILE,
            key_passphrase=self.CERT_PASSPHRASE,
        )
        if self.signer == None:
            print("Error while opening PFX file.")
        return self.signer

    # Settings for PAdES-LTA
    def signatureMeta(self):
        self.signature_meta = signers.PdfSignatureMetadata(
            field_name="SignatureIdo1ne",
            md_algorithm="sha256",
            # Mark the signature as a PAdES signature
            subfilter=SigSeedSubFilter.PADES,
            # We'll also need a validation context
            # to fetch & embed revocation info.
            # validation_context=ValidationContext(allow_fetching=True),
            # Embed relevant OCSP responses / CRLs (PAdES-LT)
            # embed_validation_info=True,
            # Tell pyHanko to put in an extra DocumentTimeStamp
            # to kick off the PAdES-LTA timestamp chain.
            use_pades_lta=True,
            signer_key_usage={"non_repudiation"},
        )

    # Application de la signature
    def applySignature(self, infile, outfile):
        with open(infile, "rb") as inf:
            # needed to avoid pyhanko.sign.general.SigningError: Attempting to sign document with hybrid cross-reference sections while hybrid xrefs are disabled
            w = IncrementalPdfFileWriter(inf, strict=False)
            fields.append_signature_field(
                w,
                sig_field_spec=fields.SigFieldSpec(
                    "SignatureIdo1ne",
                    box=(30, 300, 150, 330),
                ),
            )

            meta = signers.PdfSignatureMetadata(field_name="SignatureIdo1ne")

            pdf_signer = signers.PdfSigner(
                meta,
                signer=self.signer,
                stamp_style=stamp.QRStampStyle(
                    # Let's include the URL in the stamp text as well
                    stamp_text="Signed by: %(signer)s\n\nTime: %(ts)s\n\nURL: %(url)s",
                    text_box_style=text.TextBoxStyle(
                        font=opentype.GlyphAccumulatorFactory(self.STAMP_FONT),
                    ),
                ),
            )

            """"
            meta = signers.PdfSignatureMetadata(field_name='Signature')
            pdf_signer = signers.PdfSigner(
                meta, signer=self.signer, stamp_style=stamp.QRStampStyle(
                    # Let's include the URL in the stamp text as well
                    stamp_text='Signed by: %(signer)s\n\nTime: %(ts)s\n\nURL: %(url)s',
                    text_box_style=text.TextBoxStyle(
                        font=opentype.GlyphAccumulatorFactory(self.STAMP_FONT)
                    ),
                ),
            )
            """

            with open(outfile, "wb") as outf:
                signers.sign_pdf(
                    w,
                    self.signature_meta,
                    self.signer,
                    output=outf,
                )

    @staticmethod
    def check_already_signed(doc_id):
        MEDIA_ROOT = settings.MEDIA_ROOT
        STAMPS_DIR = MEDIA_ROOT / "stamps"

        with open(f"{STAMPS_DIR}/{doc_id}.pdf", "rb") as doc:
            r = PdfFileReader(doc)
            if len(r.embedded_signatures) == 0:
                logger.debug(
                    f"No embedded signatures found in {STAMPS_DIR}/{doc_id}.pdf",
                )
                return False
            else:
                sig = r.embedded_signatures[0]
                if sig.field_name == "SignatureIdo1ne":
                    logger.debug(sig.field_name + " is already present")
                    return True
                else:
                    logger.debug(
                        "an other signature"
                        + sig.field_name
                        + "is already present but not SignatureIdo1ne",
                    )
                    return False
