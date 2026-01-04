from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields
from pyhanko.sign import signers


class StampDocument:
    CERT_PATH_FILE = "c:/temp/df/cert.p12"
    CERT_CHAIN_FILE = "c:/temp/df/chain.cer"
    CERT_PASSPHRASE = b"l1O!Yutd@XTceY2D"
    STAMP_FONT = "c:/temp/df/NotoSans-Regular.ttf"
    IN = "c:/temp/df/essai.pdf"
    OUT = "c:/temp/df/out.pdf"
    MODEL = "c:/temp/df/watermark.pdf"

    def __init__(self):
        self.createSignerpkcs()

    def createSignerpkcs(self):
        self.signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=self.CERT_PATH_FILE,
            passphrase=self.CERT_PASSPHRASE,
        )

    def applyStamp(self, inFile, outFile):
        with open(inFile, "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            fields.append_signature_field(
                w,
                sig_field_spec=fields.SigFieldSpec(
                    "Signature",
                    box=(200, 600, 400, 660),
                ),
            )

            meta = signers.PdfSignatureMetadata(field_name="Signature")
            pdf_signer = signers.PdfSigner(
                meta,
                signer=self.signer,
                stamp_style=stamp.StaticStampStyle.from_pdf_file(self.MODEL),
            )
            with open(outFile, "wb") as outf:
                pdf_signer.sign_pdf(w, output=outf)
