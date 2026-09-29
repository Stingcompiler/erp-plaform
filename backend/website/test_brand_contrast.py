from django.template import Context, Template
from django.test import SimpleTestCase

from website.templatetags.brand_contrast import _rgb, contrast, readable, text_on

LIGHT = ["#ffffff", "#f6f8f7"]
DARK = ["#16232c", "#0f1a22"]


class BrandContrastTests(SimpleTestCase):
    def assertReadable(self, colour, grounds):
        for ground in grounds:
            self.assertGreaterEqual(contrast(_rgb(colour), _rgb(ground)), 4.5, (colour, ground))

    def test_a_dark_brand_is_lightened_on_the_dark_theme(self):
        # The review measured 1.1:1 for a navy brand on the dark surface.
        self.assertLess(contrast(_rgb("#1e2a38"), _rgb("#16232c")), 1.5)
        self.assertReadable(readable("#1e2a38", DARK), DARK)

    def test_a_pale_brand_is_darkened_on_the_light_theme(self):
        self.assertReadable(readable("#facc15", LIGHT), LIGHT)
        self.assertReadable(readable("#fff", LIGHT), LIGHT)

    def test_a_brand_that_already_reads_is_kept(self):
        self.assertEqual(readable("#0f5132", LIGHT), "#0f5132")

    def test_button_text_on_the_brand(self):
        self.assertEqual(text_on("#111827"), "#ffffff")
        self.assertEqual(text_on("#facc15"), "#14202c")

    def test_the_filters_render_in_a_template(self):
        out = Template(
            '{% load brand_contrast %}{{ c|readable_on:"#16232c,#0f1a22" }}|{{ c|text_on }}'
        ).render(Context({"c": "#111827"}))
        ink, on = out.split("|")
        self.assertReadable(ink, DARK)
        self.assertEqual(on, "#ffffff")
