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

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from paperless import settings
from paperless.celery import app

from paperless_stamp.sign import SignDocument


logger = logging.getLogger("paperless.handlers")
#make a new logger instance
mylogger = logging.getLogger("paperless_stamp")
file_handler = logging.FileHandler(settings.LOGGING_DIR / "paperless_stamp.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
mylogger.addHandler(file_handler)
mylogger.setLevel(logging.DEBUG)

@csrf_exempt  # This is to disable CSRF validation for the incoming POST requests
def webhook(request):
    if request.method == "POST" and "webhook" in request.path and CreateInterfaceUser():
        try:
            mylogger.debug("Webook detecting : updating in progress")
            doc_url = request.POST.get("doc_url")

            if doc_url:
                mylogger.debug("Fetching PDF from URL: %s", doc_url)
                doc_id = doc_url.strip("/").split("/")[-1]
                mylogger.debug("Extracted doc ID: %s", doc_id)
                document = Documents(doc_id=doc_id)

                # Download document to test if signature already exists
                Documents.download_file_pdf(doc_id)

                mylogger.debug("Tests if document is already publishing by testing signature presence",)
                if not SignDocument.check_already_signed(doc_id):
                    logger.debug("not ever signed, published")
                    ##task=process_document_task.delay(doc_id, api_client)
                    #   ### Enchaine les taches et envoi le resultat à la suivante si la tâche est SUCCESS
                    #   ##result = process_document_task.apply_async(args=(doc_id, api_client), link=get_stat_of_task.s())
                    result = chain(
                        document.process_document_task.s(document),
                        document.get_stat_of_task.s(previous_doc=document),
                        document.post_send_signed_doc.s(previous_doc=document),
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

        #API User
        self.username = os.getenv("PAPERLESS_IDO1NE_INTERNAL_INTERFACE_USER","internalInterfaceIdo1ne",)
        self.password = os.getenv("PAPERLESS_IDO1NE_INTERNAL_INTERFACE_PASSPHRASE","kvHZZ0t$TY&sWCfy7#W",)
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
        response = requests.patch(url, headers=self.headers, json=data)
        logger.debug("PATCH %s response: %s", url, response.content)
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
        STAMPS_DIR,CERTS_DIR,BASE_SIGN=self.checkAndSetfolder()
        # self.cf_date_de_debut_de_publication = "2020-11-23"
        # self.cf_date_de_fin_de_publication = "2020-11-26"
        # self.cf_annexes_a_publier = [43,42]  # Example IDs for annexes to publish
        self.cf_annexes_a_publier = []
        self.shared_link_id = ""
        self.doc_correspondent= ""
        self.doc_signataire= None

        self.filenotsigned=f"{STAMPS_DIR}/{self.doc_id}.pdf"
        self.filesigned=f"{STAMPS_DIR}/{self.doc_id}_sign.pdf"
        self.fileorginalmeta=f"{STAMPS_DIR}/{self.doc_id}_metadata.json"
        self.filenewmeta=f"{STAMPS_DIR}/{self.doc_id}_metadata_modified.json"
        self.basesignataires=f"{BASE_SIGN}/signataires.json"

    @staticmethod
    def checkAndSetfolder():
        try:
            MEDIA_ROOT = settings.MEDIA_ROOT
            STAMPS_DIR = MEDIA_ROOT / "stamps"
            CERTS_DIR = MEDIA_ROOT / "certs"
            BASE_SIGN = MEDIA_ROOT / "base_signataires"

            logger.debug(f"Check Stamp dir {STAMPS_DIR} and Certs dir {CERTS_DIR} exists")
            if not STAMPS_DIR.exists():
                STAMPS_DIR.mkdir(parents=True)
            if not CERTS_DIR.exists():
                CERTS_DIR.mkdir(parents=True)
            if not BASE_SIGN.exists():
                BASE_SIGN.mkdir(parents=True)
            if STAMPS_DIR.exists() and CERTS_DIR.exists() and BASE_SIGN.exists() :
                logger.debug(f"Initialize Stamp dir {STAMPS_DIR}, Certs {CERTS_DIR}, Base signataires {BASE_SIGN}")
                return STAMPS_DIR,CERTS_DIR,BASE_SIGN
            else :
                return False
        except:
            raise Exception(f"Failed to initialize Stamp dir {STAMPS_DIR} and {CERTS_DIR}")

    @shared_task
    # Tâche principal de signature
    def process_document_task(self):
        #sign_client = SignAndStampDocument()
        self.load_from_api()
        self.save_original_metadata_by_api()
        self.load_original_metadata_from_file()
        self.download_pdf()
        self.display_document_json_data()

        logger.debug("Test if document could be signed")

        # retrieve signataire from base_signataires
        signataire=self.get_signataire_from_file(self.doc_correspondent)
        logger.debug(f"signataire found : {signataire}")

        # if signataire is found in pseudodatabase
        if signataire is not None:
            sign_client=SignDocument(input=self.filenotsigned,
                                output=self.filesigned,
                                qr_url="http://exemple.com",
                                text_params={'url': 'https://example.com','signer':signataire,'date':'06/01/2025','checksum':'0f12df21sdf154'})
            logger.debug("Document %s was SIGNED successfully.", self.doc_id)

            last_id = self.get_last_id_of_document()

            logger.debug(f"Create a sharing link on {last_id}")
            self.make_a_sharing_link(last_id)
            self.delete_original_document()
            self.empty_original_document_from_trash()
            uuidtask = self.post_new_document(self.filesigned)

        """
        if len(self.cf_annexes_a_publier)>0:
            for i in self.cf_annexes_a_publier:
                self.process_document_task(Documents(doc_id=i))
        """

        logger.debug("Document %s was SIGNED and posted with UUID: %s",self.doc_id,uuidtask,)
        return uuidtask

    def load_from_api(self):
        if self.doc_id:
            data = self.api_client.get("documents/" + self.doc_id + "/" + "?full_perms=true",).json()
            self.doc_id = str(data.get("id"))
            self.doc_correspondent=str(data.get("correspondent"))

            return Documents
        else:
            raise Exception(f"Failed to load document with id {self.doc_id}")

    def save_original_metadata_by_api(self):
        # doc_url="http://localhost:8000/api/documents/"+self.doc_id+"/"
        if self.doc_id:
            data = self.api_client.get("documents/" + self.doc_id + "/")
            # write metadata to file
            open(self.fileorginalmeta, "w").write(data.text)
        else:
            raise Exception(f"Failed to load document with id {self.doc_id}")

    def load_original_metadata_from_file(self):
        if self.doc_id:
            data = open(self.fileorginalmeta).read()
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
            self.doc_correspondent=datajson["correspondent"]
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
            open(self.filenewmeta, "w").write(
                json.dumps(datajson),
            )
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

    def get_group_id_in_relation_with_correspondant(self,previous_doc):
        api_client = APIClient()
        data = api_client.get("correspondents/"+str(previous_doc.doc_correspondent)+"/"+"?full_perms=true").json()
        if data:
            group_id_in_relation_with_correspondant = data['permissions']['view']['groups']
            logger.debug(f"Group ID in relation with the correspondant {group_id_in_relation_with_correspondant}")
            return group_id_in_relation_with_correspondant


    def download_pdf(self):
        if self.doc_id:
            pdf = self.api_client.get("documents/" + self.doc_id + "/download/")
            open(self.filenotsigned, "wb").write(pdf.content)
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
            data = open(self.fileorginalmeta).read()
            data = json.loads(data)

            logger.debug("Document JSON Data: %s", json.dumps(data, indent=4))
            mylogger.debug("Document JSON Data: %s", json.dumps(data, indent=4))
        else:
            raise Exception(f"Failed to load document with id {self.doc_id} from file")

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
        logger.debug("Ensuring stamps directory exists at: %s", self.STAMPS_DIR)
        if not self.STAMPS_DIR.exists():
            self.STAMPS_DIR.mkdir(parents=True)

        if os.path.exists(f"{self.STAMPS_DIR}/{self.doc_id}.pdf"):
            files = {"document": open(f"{self.STAMPS_DIR}/{self.doc_id}.pdf", "rb")}
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
        if os.path.exists(self.filesigned):
            files = {"document": open(f"{signed_doc_path}", "rb")}
            data = open(self.filenewmeta).read()
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

    def set_new_right(self,previous_doc):
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
        public_user_group=self.get_id_of_public_group()
        group_id_in_relation_with_correspondant=self.get_group_id_in_relation_with_correspondant(previous_doc)
        # concat int public_user_group and one or many group
        group_value=[public_user_group]+group_id_in_relation_with_correspondant

        data = {
        "owner": public_user_id,
        "set_permissions": { "view": { "groups": group_value } }
        }
        response = self.api_client.patch_right(
            endpoint="documents/" + self.doc_id + "/",
            data=data,
        ).json()
        if response.get("owner") == public_user_id:
            logger.debug(f"set new rights with public user ({public_user_id})")

    def get_last_id_of_document(self):
        # dernier document publié
        owner = self.get_id_of_public_user()
        response = self.api_client.get(
            f"documents/?ordering=-id&owner__id={owner}",
        ).json()
        if response.get("results"):
            last_doc_id = response["results"][0]["id"]
            return last_doc_id

    def delete_temporary_files(self):
        try:
            if os.path.exists(self.filenotsigned):
                os.remove(self.filenotsigned)
            if os.path.exists(self.filesigned):
                os.remove(self.filesigned)
            if os.path.exists(self.fileorginalmeta):
                os.remove(self.fileorginalmeta)
            if os.path.exists(self.filenewmeta):
                os.remove(self.filenewmeta)
            logger.debug("Temporary files deleted successfully.")
        except Exception as e:
            logger.error("Error deleting temporary files: %s", str(e))

    def get_signataire_from_file(self,id_correspondant):
        with open(self.basesignataires, 'r') as file:
            # Load the JSON data
            data = json.load(file)
            try:
                signataire=data.get(id_correspondant)
                for k, v in data.items():
                    if k == str(id_correspondant):
                        logger.debug(f"signataire found in file : {v}")
                        return v
            except:
                logger.debug(f"signataires not found")

            return data

    @app.task
    # Récupère l'état de la tâche pour déterminer si le POSTing du document signé est terminé
    def get_stat_of_task(uuid, previous_doc):
        api_client = APIClient()
        # logger.debug(f"task to check{uuid}")
        response = api_client.get_task_status(uuidtask=uuid)
        data = response.json()
        related_document = data[0].get("related_document")
        # logger.debug("Task JSON Data: %s", json.dumps(data, indent=4))
        logger.debug(f" Related document is : {related_document}")
        #time.sleep(5)
        #logger.debug("RETRIERVE NEW TWO TASK")
        #logger.debug(f"PREVIOUS DOC HAS {previous_doc.doc_id}")
        return related_document

    @app.task
    # Exécute le traitement post-signature du document : ajout des droits, replacement du permalien sur le document signé
    def post_send_signed_doc(related_document, previous_doc):
        try:
            newdoc = Documents(doc_id=related_document)
            newdoc.set_new_right(previous_doc=previous_doc)
            newdoc.modify_shared_link(shared_link_id=previous_doc.shared_link_id)
            newdoc.delete_temporary_files()
            previous_doc.delete_temporary_files()

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}



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

