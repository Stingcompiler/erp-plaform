"""Payment proofs are identified by their bytes and served as attachments
(review F07): SVG, HTML and polyglots are refused whatever the client
labels them, and a stored proof never renders inline in the app origin."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from core.uploads import sniff, validate_proof

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 32
PDF = b"%PDF-1.4\n" + b"0" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<!doctype html><html><script>1</script></html>"


def upload(name, data, content_type):
    return SimpleUploadedFile(name, data, content_type=content_type)


class SniffTests(TestCase):
    def test_recognises_real_images_and_pdf(self):
        for data, mime in ((PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"),
                           (PDF, "application/pdf")):
            self.assertEqual(sniff(upload("x", data, "application/octet-stream"))[0], mime)

    def test_svg_html_and_empty_are_unknown(self):
        for data in (SVG, HTML, b""):
            self.assertEqual(sniff(upload("x", data, "image/png")), (None, None))


class ValidateProofTests(TestCase):
    def test_label_does_not_matter_only_bytes_do(self):
        # An SVG named .png and labelled image/png is refused…
        with self.assertRaises(ValidationError):
            validate_proof(upload("receipt.png", SVG, "image/png"), max_bytes=1 << 20)
        with self.assertRaises(ValidationError):
            validate_proof(upload("receipt.jpg", HTML, "image/jpeg"), max_bytes=1 << 20)
        # …and a real JPEG named .svg with a wrong label is accepted and renamed.
        f = upload("screenshot.svg", JPEG, "image/svg+xml")
        self.assertEqual(validate_proof(f, max_bytes=1 << 20), "image/jpeg")
        self.assertEqual(f.name, "screenshot.jpg")

    def test_pdf_only_where_allowed_and_size_capped(self):
        with self.assertRaises(ValidationError):
            validate_proof(upload("p.pdf", PDF, "application/pdf"), max_bytes=1 << 20)
        self.assertEqual(
            validate_proof(upload("p.pdf", PDF, "application/pdf"), max_bytes=1 << 20,
                           allow_pdf=True),
            "application/pdf",
        )
        with self.assertRaises(ValidationError):
            validate_proof(upload("big.png", PNG, "image/png"), max_bytes=10)
