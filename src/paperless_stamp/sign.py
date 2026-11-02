from pathlib import Path
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields,signers
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko_certvalidator import ValidationContext
from pyhanko import stamp
from pyhanko.pdf_utils import text
from pyhanko.pdf_utils.font import opentype
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from pyhanko.pdf_utils.layout import AxisAlignment, Margins, SimpleBoxLayoutRule, BoxConstraints
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.stamp import QRPosition,QRStampStyle,QRStamp,TextStamp
from pyhanko.pdf_utils.text import TextBoxStyle
from paperless import settings
import logging
import os


logger = logging.getLogger("paperless.handlers")


class SignDocument:
    try:
        MEDIA_ROOT = settings.MEDIA_ROOT  # Ensure MEDIA_ROOT is a Path object
        CERTS_DIR = MEDIA_ROOT / "certs"
        if not CERTS_DIR.exists():
            CERTS_DIR.mkdir(parents=True)
        CERTS_DIR = str(CERTS_DIR)
    except:
        raise Exception(f"Failed to initialize Stamp dir {CERTS_DIR}")

    # certificate in p12 format
    CERT_PATH_FILE_P12 = CERTS_DIR + "/cert.p12"
    CERT_PASSPHRASE_P12 = b"l1O!Yutd@XTceY2D"
    # certificate in pem format
    CERT_PATH_FILE = CERTS_DIR + "/domain.crt"
    CERT_KEY_FILE = CERTS_DIR + "/domain.key"
    CERT_PASSPHRASE = b"PASSPHRASE"
    STAMP_FONT = CERTS_DIR + "/NotoSans-Regular.ttf"
    TRUST_CA_CERT = CERTS_DIR + "/chain.cer"

    #box pour contenir le timbre
    bcstamp=BoxConstraints(width=120,height=22)
    #box pour contenir la mention page x sur X
    bcpagestamp=BoxConstraints(width=8,height=5)

    zero_margins = SimpleBoxLayoutRule(
        x_align=AxisAlignment.ALIGN_MID,
        y_align=AxisAlignment.ALIGN_MID,
        margins=Margins(5,5,5,5),
    )

    style = QRStampStyle(
            border_width=0.3,
            stamp_text="Publié le %(date)s, par %(signer)s\nPreuve d'intégrité: %(checksum)s\n\nDocument publié conforme à l'original",
            text_box_style=TextBoxStyle(font=opentype.GlyphAccumulatorFactory(STAMP_FONT),box_layout_rule=SimpleBoxLayoutRule(x_align=2, y_align=2, margins=Margins(top=2, left=5, bottom=2, right=5))),
            qr_position=QRPosition.LEFT_OF_TEXT,
            #background=STAMP_ART_CONTENT,  # Built-in stamp background
            background_opacity=0.6,
            #background_layout=SimpleBoxLayoutRule(x_align=5, y_align=5, margins=Margins(top=2,bottom=2)),
            #qr_inner_size=22,
        )

    page_style= stamp.TextStampStyle(
        border_width=0,
        # the 'signer' and 'ts' parameters will be interpolated by pyHanko, if present
        stamp_text='page %(i)s/%(total_page)s',
        text_box_style=TextBoxStyle(font=opentype.GlyphAccumulatorFactory(STAMP_FONT),box_layout_rule=SimpleBoxLayoutRule(x_align=2, y_align=2, margins=Margins(top=0, left=5, bottom=1, right=0)))
        )

    def __init__(self,input,output,qr_url,text_params) :
        self.input=input
        self.output=output
        self.qr_url=qr_url
        self.text_params=text_params

        #if SignDocument.check_already_signed(self.input):
        #    print("already sign")
        #else:
        self.signer=self.createSignerpkcs()
        self.signature_meta=self.signatureMeta()
        self.applySignature()

    #récupération des infos du certificat
    def createSignerpkcs(self):
        signer = signers.SimpleSigner.load(cert_file=self.CERT_PATH_FILE, key_file=self.CERT_KEY_FILE,key_passphrase=self.CERT_PASSPHRASE)
        if signer == None:
            print("Error while opening PFX file.")
        return signer

    # Settings for PAdES-LTA
    @classmethod
    def signatureMeta(self):
        signature_meta = signers.PdfSignatureMetadata(
        field_name='SignatureIdo1ne', md_algorithm='sha256',
        # Mark the signature as a PAdES signature
        subfilter=SigSeedSubFilter.PADES,
        # We'll also need a validation context
        # to fetch & embed revocation info.
        validation_context=ValidationContext(allow_fetching=True),
        # Embed relevant OCSP responses / CRLs (PAdES-LT)
        embed_validation_info=True,
        # Tell pyHanko to put in an extra DocumentTimeStamp
        # to kick off the PAdES-LTA timestamp chain.
        use_pades_lta=True,
        #certify=True,
        signer_key_usage={'non_repudiation'},
        )
        return signature_meta

    #Application de la signature
    def applySignature(self):
        print(f"signature en cours sur {self.input}")
        with open(self.input, 'rb') as inf:
            w = IncrementalPdfFileWriter(inf, strict=False)

            #Prequis signature
            meta = signers.PdfSignatureMetadata(field_name='SignatureIdo1ne')
            fields.append_signature_field(w, sig_field_spec=fields.SigFieldSpec('SignatureIdo1ne', box=(15, 20, 135, 42),on_page=0))
            pdf_signer = signers.PdfSigner(meta, signer=self.signer, stamp_style=self.style)

            #Prerequis stamp
            total_page=self.page_count(self.input)

            #Applique le tampon
            for i in range(1,total_page):
                #print(f"page {i} sur {total_page}")
                mystamp = QRStamp(writer=w, style=self.style,url=self.qr_url,text_params=self.text_params,box=self.bcstamp)
                mypagestamp = TextStamp(writer=w, style=self.page_style,text_params={'i':i,'total_page':total_page},box=self.bcpagestamp)
                mypagestamp.apply(dest_page=i, x=15, y=20)
                mystamp.apply(dest_page=i, x=10, y=20)


            with open(self.output, 'wb') as outf:
                #applique la signature
                print(f"signature en cours sur {self.output}")
                pdf_signer.sign_pdf(w, output=outf, appearance_text_params=self.text_params)
                #pdf_signer.sign_pdf(w, self.signature_meta, self.signer, output=outf)

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
                os.remove(f"{STAMPS_DIR}/{doc_id}.pdf")
                return False
            else:
                sig = r.embedded_signatures[0]
                if sig.field_name == "SignatureIdo1ne":
                    logger.debug(sig.field_name + " is already present")
                    # delete the temporary file
                    os.remove(f"{STAMPS_DIR}/{doc_id}.pdf")
                    return True
                else:
                    logger.debug(
                        "an other signature"
                        + sig.field_name
                        + "is already present but not SignatureIdo1ne",
                    )
                    os.remove(f"{STAMPS_DIR}/{doc_id}.pdf")
                    return False



    @classmethod
    def page_count(cls,inputFile):
        try:
            with open(inputFile,"rb") as doc:
                r=PdfFileReader(doc)
                page_count=(int(r.root['/Pages']['/Count']))
        except:
            print("cannot open the file", {e})
        return page_count
