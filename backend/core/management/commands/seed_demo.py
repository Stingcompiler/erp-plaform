"""Fill a real company with demo data so its workspace and public page look
lived-in: catalogue, stock, customers with debts, suppliers, CRM leads, a
month of sales, and a complete published company page with generated
pictures. The company is marked `is_demo`, so its public page and its
showcase card carry a visible "demo company" label.

Meant for a demo tenant on the hosted platform or a fresh install, run by
an operator who can reach `manage.py` (Render shell, SSH). It never asks
for a password: it takes the owner's email and works inside that owner's
company, and every write goes through the same serializers and views the
app uses, so numbering, stock movements, payments and audit rows are the
real thing.

    python manage.py seed_demo --owner owner@example.com --yes
    python manage.py seed_demo --owner … --sales 60 --days 30 --yes
    python manage.py seed_demo --platform --yes     # demo leads + registrations
    python manage.py seed_demo --owner … --scale 2500 --yes   # prices in SDG
    python manage.py seed_demo --owner … --lang en --yes      # English names

The catalogue, customers, suppliers, leads and the public page are written in
Arabic by default; `--lang en` writes the same rows in English (for an
English-speaking demo company and the English marketing screenshots, see
frontend/scripts/marketing-shots.mjs). Numbers, SKUs and phones are the same.

The catalogue's prices are written in US dollars. A company that works in
another currency passes `--scale` (units of its currency per dollar): every
cost, price and CRM deal value is multiplied by it and rounded to a figure a
shop would print — for the Sudanese pound, 2500 turns a 1.20 kilo of sugar
into 3,000 ج.س and a 0.40 bottle of water into 1,000 ج.س.

Master data is idempotent (SKUs DEMO-001…, names looked up by company);
sales are added on every run (`--sales 0` to skip). Pictures are simple
generated tiles (no fonts needed) so the page counts as complete; replace
them from the site editor whenever real photos exist.
"""
import argparse
import io
import random
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from core.public_media import stored_public_url

DEMO_PREFIX = "DEMO-"

CATEGORIES = ["مواد غذائية", "مشروبات", "منظفات", "أدوات منزلية", "عناية شخصية"]
UNITS = [("قطعة", "pc"), ("كرتون", "ctn"), ("كيلو", "kg")]

# (name, category, unit, cost, price, opening stock, reorder level) — cost and
# price in US dollars; `--scale` converts them (see _scaled).
PRODUCTS = [
    ("سكر 1 كجم", 0, "kg", "0.90", "1.20", 180, 40),
    ("أرز بسمتي 5 كجم", 0, "pc", "6.50", "8.90", 60, 15),
    ("زيت طعام 1.8 لتر", 0, "pc", "3.20", "4.30", 75, 20),
    ("دقيق 2 كجم", 0, "pc", "1.60", "2.10", 90, 25),
    ("عدس أحمر 1 كجم", 0, "kg", "1.10", "1.60", 70, 20),
    ("شاي أسود 250 جم", 0, "pc", "1.40", "2.00", 120, 30),
    ("معكرونة 500 جم", 0, "pc", "0.55", "0.80", 200, 50),
    ("طماطم معلبة 400 جم", 0, "pc", "0.60", "0.95", 140, 30),
    ("مياه معدنية 1.5 لتر", 1, "pc", "0.25", "0.40", 300, 80),
    ("عصير برتقال 1 لتر", 1, "pc", "0.90", "1.30", 80, 20),
    ("مشروب غازي 330 مل", 1, "pc", "0.30", "0.50", 240, 60),
    ("حليب طويل الأجل 1 لتر", 1, "pc", "0.85", "1.20", 110, 30),
    ("مسحوق غسيل 3 كجم", 2, "pc", "3.80", "5.20", 45, 10),
    ("سائل جلي 1 لتر", 2, "pc", "0.95", "1.40", 85, 20),
    ("مطهر أرضيات 2 لتر", 2, "pc", "1.50", "2.20", 60, 15),
    ("مناديل ورقية 200 منديل", 2, "pc", "0.70", "1.00", 150, 40),
    ("طقم أكواب زجاج 6 قطع", 3, "pc", "2.40", "3.60", 30, 8),
    ("مقلاة تيفال 26 سم", 3, "pc", "6.00", "8.50", 18, 5),
    ("سلة غسيل بلاستيك", 3, "pc", "1.80", "2.70", 25, 6),
    ("مصباح LED 12 واط", 3, "pc", "0.80", "1.30", 95, 25),
    ("شامبو 400 مل", 4, "pc", "1.60", "2.40", 70, 20),
    ("صابون 125 جم (3 قطع)", 4, "pc", "0.75", "1.10", 130, 30),
    ("معجون أسنان 100 مل", 4, "pc", "0.65", "1.00", 110, 30),
    ("حفاضات أطفال مقاس 4", 4, "ctn", "9.50", "12.90", 22, 6),
]

CUSTOMERS = [
    ("بقالة النور", "0912 100 200", "حي الرياض"),
    ("سوبر ماركت الأمانة", "0912 300 400", "الخرطوم 2"),
    ("مطعم الضيافة", "0911 555 666", "العمارات"),
    ("محمد عثمان", "0999 777 888", ""),
    ("كافتيريا الجامعة", "0918 222 333", "شارع الجامعة"),
    ("بقالة الحي", "0910 444 555", "حي بري، الخرطوم"),
    ("فاطمة الطاهر", "0996 123 456", ""),
    ("مخبز الفجر", "0915 987 654", "الكلاكلة"),
]

SUPPLIERS = [
    ("شركة النيل للتوزيع", "0183 000 111", "sales@nile-dist.example"),
    ("مصنع الأمل للمنظفات", "0183 222 333", "orders@amal.example"),
    ("مستوردون متحدون", "0912 888 999", ""),
    ("مزارع الجزيرة", "0918 111 222", ""),
]

LEADS = [
    ("سلسلة متاجر الواحة", "أحمد الفاتح", "0912 654 321", "معرض", "qualified", "45000"),
    ("مطاعم البركة", "سارة عبدالله", "0911 321 654", "توصية", "contacted", "12000"),
    ("صيدلية الشفاء", "د. خالد", "0999 111 000", "الموقع", "new", "8000"),
    ("موزع الشرق", "عمر حسن", "0918 000 999", "مكالمة", "proposal", "70000"),
    ("بقالة السلام", "ليلى", "0910 222 111", "الموقع", "new", "3000"),
]

SERVICES = ["توصيل للمنازل", "بيع بالجملة", "تقسيط مريح", "طلبات عبر واتساب"]
SENDER_BANKS = ["بنك فيصل", "بنك أم درمان", "بنكك"]

# The same demo company in English (`--lang en`): the rows above, by index.
PRODUCT_NAMES_EN = [
    "Sugar 1 kg", "Basmati rice 5 kg", "Cooking oil 1.8 L", "Flour 2 kg", "Red lentils 1 kg",
    "Black tea 250 g", "Pasta 500 g", "Canned tomatoes 400 g", "Mineral water 1.5 L",
    "Orange juice 1 L", "Soft drink 330 ml", "UHT milk 1 L", "Washing powder 3 kg",
    "Dish soap 1 L", "Floor cleaner 2 L", "Tissues (200)", "Glass set (6 pcs)",
    "Frying pan 26 cm", "Plastic laundry basket", "LED bulb 12 W", "Shampoo 400 ml",
    "Soap 125 g (3 bars)", "Toothpaste 100 ml", "Baby diapers size 4",
]
ENGLISH = {
    "categories": ["Groceries", "Beverages", "Cleaning", "Household", "Personal care"],
    "units": [("Piece", "pc"), ("Carton", "ctn"), ("Kilo", "kg")],
    "customers": [
        ("Al Noor Grocery", "0912 100 200", "Al Riyadh"),
        ("Al Amana Supermarket", "0912 300 400", "Khartoum 2"),
        ("Al Diyafa Restaurant", "0911 555 666", "Al Amarat"),
        ("Mohamed Osman", "0999 777 888", ""),
        ("University Cafeteria", "0918 222 333", "University Street"),
        ("Neighbourhood Grocery", "0910 444 555", "Burri, Khartoum"),
        ("Fatima Altahir", "0996 123 456", ""),
        ("Al Fajr Bakery", "0915 987 654", "Al Kalakla"),
    ],
    "suppliers": [
        ("Nile Distribution Co.", "0183 000 111", "sales@nile-dist.example"),
        ("Al Amal Detergents", "0183 222 333", "orders@amal.example"),
        ("United Importers", "0912 888 999", ""),
        ("Gezira Farms", "0918 111 222", ""),
    ],
    "leads": [
        ("Al Waha Stores", "Ahmed Alfatih", "0912 654 321", "Trade fair", "qualified", "45000"),
        ("Al Baraka Restaurants", "Sara Abdalla", "0911 321 654", "Referral", "contacted",
         "12000"),
        ("Al Shifa Pharmacy", "Dr. Khalid", "0999 111 000", "Website", "new", "8000"),
        ("East Distributor", "Omar Hassan", "0918 000 999", "Phone call", "proposal", "70000"),
        ("Al Salam Grocery", "Laila", "0910 222 111", "Website", "new", "3000"),
    ],
    "services": ["Home delivery", "Wholesale", "Instalments", "Orders on WhatsApp"],
    "sender_banks": ["Faisal Islamic Bank", "Omdurman National Bank", "Bankak"],
    "branch": "Main branch", "warehouse": "Main warehouse", "bank": "Bank of Khartoum",
    "note": "First contact made; interested in a wholesale quote.",
    "follow_up": "Follow up on the quote",
    "tagline": "Wholesale prices, fast delivery and credit for our regular customers",
    "about": (
        "For years we have served groceries, restaurants and families with food, "
        "cleaning and household goods at wholesale prices, delivered the same day "
        "anywhere in town."
    ),
    "address": "Market Street, Block 5", "city": "Khartoum",
    "hours": "Saturday - Thursday 8am - 10pm\nFriday 4pm - 10pm",
    "sections": [("Best sellers", "Wholesale prices start from one carton."),
                 ("", "Visit us at the market or message us on WhatsApp.")],
    "caption": "Wholesale price per unit",
}
ARABIC = {
    "categories": CATEGORIES, "units": UNITS, "customers": CUSTOMERS,
    "suppliers": SUPPLIERS, "leads": LEADS, "services": SERVICES,
    "sender_banks": SENDER_BANKS,
    "branch": "الفرع الرئيسي", "warehouse": "المخزن الرئيسي", "bank": "بنك الخرطوم",
    "note": "تم التواصل الأول؛ مهتم بعرض سعر للجملة.",
    "follow_up": "متابعة عرض السعر",
    "tagline": "أسعار جملة، توصيل سريع، وحساب آجل لعملائنا الدائمين",
    "about": (
        "نخدم البقالات والمطاعم والأسر منذ سنوات بتشكيلة مواد غذائية ومنظفات "
        "وأدوات منزلية بأسعار الجملة، مع توصيل في اليوم نفسه داخل المدينة."
    ),
    "address": "شارع السوق، مربع 5", "city": "الخرطوم",
    "hours": "السبت - الخميس 8ص - 10م\nالجمعة 4م - 10م",
    "sections": [("الأكثر طلبًا", "أسعار الجملة تبدأ من كرتون واحد."),
                 ("", "زورونا في السوق أو راسلونا على واتساب.")],
    "caption": "سعر الجملة لكل وحدة",
}
CONTENT = {"ar": ARABIC, "en": ENGLISH}

PLATFORM_LEADS = [
    ("متجر الفردوس (تجريبي)", "0912 010 010", "", "whatsapp", "أريد عرضًا لمحلين"),
    ("شركة الهدى للتوزيع (تجريبي)", "0999 020 020", "huda@example.com", "call",
     "هل يدعم النظام الجملة؟"),
    ("صيدلية النخيل (تجريبي)", "", "nakheel@example.com", "email",
     "أرغب في تجربة النظام"),
]
PLATFORM_REGISTRATIONS = [
    ("مجموعة الريان التجارية (تجريبي)", "عبدالرحمن", "rayyan@example.com", "0912 030 030",
     12, 3),
    ("مخابز الصباح (تجريبي)", "منى", "sabah@example.com", "0911 040 040", 4, 1),
]


def _scaled(value, scale):
    """A dollar figure in the company's currency: `value` × `scale`, rounded
    the way a shop prices things — to 50 from a thousand up, to 5 from a
    hundred, else to the cent. `scale` 1 leaves the figure exactly as is."""
    amount = Decimal(value)
    if scale == 1:
        return amount
    amount *= scale
    if amount >= 1000:
        step = Decimal(50)
    elif amount >= 100:
        step = Decimal(5)
    else:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (amount / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def _positive_decimal(text):
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {text}") from None
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def _tile(width, height, colour, accent):
    """A PNG tile: flat colour with a lighter diagonal band — enough to make
    a page look designed without shipping any picture we do not own."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), colour)
    draw = ImageDraw.Draw(image)
    band = int(width * 0.18)
    for offset in range(-height, width, band * 2):
        draw.polygon(
            [(offset, height), (offset + band, height), (offset + band + height, 0),
             (offset + height, 0)],
            fill=accent,
        )
    out = io.BytesIO()
    image.save(out, format="PNG")
    return ContentFile(out.getvalue(), name=f"{uuid4().hex}.png")


class Command(BaseCommand):
    help = "Fill a company (by its owner's email) with realistic demo data."

    def add_arguments(self, parser):
        parser.add_argument("--owner", help="Email of the company's owner/user to seed for.")
        parser.add_argument("--sales", type=int, default=40,
                            help="POS sales to add (default 40).")
        parser.add_argument("--days", type=int, default=28,
                            help="Spread sales over the past N days.")
        parser.add_argument("--platform", action="store_true",
                            help="Also add demo leads and registration requests to the inbox.")
        parser.add_argument("--scale", type=_positive_decimal, default=Decimal(1),
                            help="Units of the company's currency per US dollar: multiplies "
                                 "the catalogue's prices and costs and CRM deal values "
                                 "(default 1; e.g. 2500 for the Sudanese pound). Applies to "
                                 "products and leads created by this run.")
        parser.add_argument("--lang", choices=sorted(CONTENT), default="ar",
                            help="Language of the names and texts it writes (default ar).")
        parser.add_argument("--seed", type=int, default=7,
                            help="Random seed for repeatable data.")
        parser.add_argument("--yes", action="store_true",
                            help="Run without the confirmation prompt.")

    def handle(self, *args, **options):
        if not options["owner"] and not options["platform"]:
            raise CommandError("Pass --owner <email> and/or --platform.")
        if not options["yes"]:
            answer = input("This writes demo rows into the database. Continue? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                raise CommandError("Aborted.")
        random.seed(options["seed"])
        self.text = CONTENT[options.get("lang") or "ar"]
        summary = []
        if options["owner"]:
            summary += self.seed_company(options["owner"], options["sales"], options["days"],
                                         Decimal(options["scale"]))
        if options["platform"]:
            summary += self.seed_platform()
        for line in summary:
            self.stdout.write(self.style.SUCCESS(line))

    # ------------------------------------------------------------ company
    def seed_company(self, email, sales, days, scale=Decimal(1)):
        from inventory.models import Category, Product, StockMovement, Unit, Warehouse
        from org.models import Branch

        user = (
            User.objects.filter(email__iexact=email).select_related("company", "role").first()
        )
        if user is None or user.company_id is None:
            raise CommandError(f"No company user with email {email}.")
        company = user.company
        out = [f"Company: {company.name} (#{company.pk}) via {user.email}"]

        with transaction.atomic():
            # A seeded company is a demo, never a real customer: its public
            # page and showcase card say so ("demo company" label).
            if not company.is_demo:
                company.is_demo = True
                company.save(update_fields=["is_demo", "updated_at"])
            out.append("Marked as a demo company (public page shows the label).")
            branch = user.branch or Branch.objects.filter(company=company).order_by("pk").first()
            if branch is None:
                branch = Branch.objects.create(
                    company=company, code="MAIN", name=self.text["branch"]
                )
            warehouse = Warehouse.objects.filter(company=company).order_by("pk").first()
            if warehouse is None:
                warehouse = Warehouse.objects.create(
                    company=company, branch=branch, name=self.text["warehouse"]
                )

            categories = [
                Category.objects.get_or_create(company=company, name=name)[0]
                for name in self.text["categories"]
            ]
            units = {
                symbol: Unit.objects.get_or_create(
                    company=company, name=name, defaults={"symbol": symbol}
                )[0]
                for name, symbol in self.text["units"]
            }
            products, created_products = [], 0
            for index, row in enumerate(PRODUCTS, start=1):
                name, cat, unit, cost, price, stock, reorder = row
                if self.text is ENGLISH:
                    name = PRODUCT_NAMES_EN[index - 1]
                product, created = Product.objects.get_or_create(
                    company=company, sku=f"{DEMO_PREFIX}{index:03d}",
                    defaults={
                        "name": name, "category": categories[cat], "unit": units[unit],
                        "barcode": f"629{index:010d}", "cost_price": _scaled(cost, scale),
                        "sale_price": _scaled(price, scale), "reorder_level": Decimal(reorder),
                    },
                )
                if created:
                    created_products += 1
                    StockMovement.objects.create(
                        company=company, product=product, warehouse=warehouse,
                        movement_type=StockMovement.ADJUSTMENT, quantity=Decimal(stock),
                        unit_cost=product.cost_price, reference_type="seed_demo",
                    )
                # A photo is (re)generated when there is none on disk — also
                # for a row whose file was lost with ephemeral storage.
                if index <= 8 and not stored_public_url(product.image):
                    product.image.save(
                        "demo.png",
                        _tile(800, 600, self._colour(index), self._colour(index, light=True)),
                        save=True,
                    )
                products.append(product)
            out.append(f"Products: {len(products)} ({created_products} new, with opening stock)")

            out += self._customers_and_suppliers(company)
            out += self._crm(company, branch, user, scale)
            out += self._website(company, products)

        if sales:
            out += self._sales(user, warehouse, products, sales, days)
        return out

    @staticmethod
    def _colour(index, light=False):
        palette = [
            (14, 124, 134), (37, 99, 235), (217, 119, 6), (5, 150, 105),
            (190, 24, 93), (79, 70, 229), (180, 83, 9), (16, 118, 110),
        ]
        r, g, b = palette[index % len(palette)]
        if light:
            return (min(r + 60, 255), min(g + 60, 255), min(b + 60, 255))
        return (r, g, b)

    def _customers_and_suppliers(self, company):
        from purchasing.models import Supplier
        from sales.models import CompanyBankAccount, Customer

        customers = 0
        for name, phone, address in self.text["customers"]:
            _, created = Customer.objects.get_or_create(
                company=company, name=name, defaults={"phone": phone, "address": address}
            )
            customers += int(created)
        suppliers = 0
        for name, phone, email in self.text["suppliers"]:
            _, created = Supplier.objects.get_or_create(
                company=company, name=name, defaults={"phone": phone, "email": email}
            )
            suppliers += int(created)
        CompanyBankAccount.objects.get_or_create(
            company=company, bank_name=self.text["bank"], account_name=company.name,
            defaults={"account_number": "0123456789"},
        )
        return [f"Customers: {customers} new", f"Suppliers: {suppliers} new"]

    def _crm(self, company, branch, user, scale=Decimal(1)):
        from crm.models import FollowUp, Lead, Note

        created = 0
        today = timezone.localdate()
        for name, contact, phone, source, stage, value in self.text["leads"]:
            lead, was_created = Lead.objects.get_or_create(
                company=company, name=name,
                defaults={
                    "branch": branch, "contact_name": contact, "phone": phone,
                    "source": source, "stage": stage,
                    "estimated_value": _scaled(value, scale),
                    "assigned_to": user, "created_by": user,
                },
            )
            if was_created:
                created += 1
                Note.objects.create(company=company, lead=lead, created_by=user,
                                    body=self.text["note"])
                FollowUp.objects.create(
                    company=company, lead=lead, created_by=user,
                    due_date=today + timedelta(days=random.randint(-3, 7)),
                    summary=self.text["follow_up"],
                )
        return [f"CRM leads: {created} new"]

    def _website(self, company, products):
        from website.models import FeaturedProduct, Section, Website

        site, _ = Website.objects.get_or_create(company=company)
        changed = []
        defaults = {
            "business_name": site.business_name or company.name,
            "tagline": self.text["tagline"],
            "about_text": self.text["about"],
            "contact_phone": site.contact_phone or "+249 91 234 5678",
            "contact_email": site.contact_email or company.email or "",
            "address": site.address or self.text["address"],
            "city": site.city or self.text["city"],
            "category": site.category or "grocery",
            "opening_hours": self.text["hours"],
            "services": "\n".join(self.text["services"]),
            "primary_color": "#0e7c86",
        }
        for field, value in defaults.items():
            if not getattr(site, field):
                setattr(site, field, value)
                changed.append(field)
        if not stored_public_url(site.cover_image):
            site.cover_image.save(
                "cover.png", _tile(1800, 700, (14, 124, 134), (52, 160, 170)), save=False
            )
            changed.append("cover_image")
        if not stored_public_url(site.logo_image):
            site.logo_image.save(
                "logo.png", _tile(512, 512, (17, 24, 39), (14, 124, 134)), save=False
            )
            changed.append("logo_image")
        site.is_published = True
        site.published_at = site.published_at or timezone.now()
        site.save()
        if not Section.objects.filter(company=company, website=site).exists():
            (products_title, products_text), (_, contact_text) = self.text["sections"]
            for order, (kind, title, text) in enumerate([
                (Section.HERO, "", ""),
                (Section.PRODUCTS, products_title, products_text),
                (Section.ABOUT, "", ""),
                (Section.CONTACT, "", contact_text),
            ]):
                Section.objects.create(company=company, website=site, type=kind, title=title,
                                       order=order, content={"text": text} if text else {})
        featured = 0
        for order, product in enumerate(products[:6]):
            _, created = FeaturedProduct.objects.get_or_create(
                company=company, website=site, product=product,
                defaults={"order": order, "caption": self.text["caption"]},
            )
            featured += int(created)
        return [f"Website: published, fields filled: {', '.join(changed) or 'none'}, "
                f"featured products: {featured} new"]

    def _sales(self, user, warehouse, products, count, days):
        from rest_framework.test import APIRequestFactory, force_authenticate

        from sales.models import CompanyBankAccount, Customer
        from sales.views import POSCheckoutView

        company = user.company
        customers = list(Customer.objects.filter(company=company, is_active=True))
        bank = CompanyBankAccount.objects.filter(company=company).first()
        factory = APIRequestFactory()
        now = timezone.now()
        made, credit, failed = 0, 0, 0
        for _ in range(count):
            lines = [
                {"product": product.pk, "quantity": str(random.randint(1, 6))}
                for product in random.sample(products, random.randint(1, 4))
            ]
            body = {
                "warehouse": warehouse.pk, "lines": lines, "client_uuid": str(uuid4()),
                "occurred_at": (
                    now - timedelta(days=random.uniform(0, days), minutes=random.randint(0, 600))
                ).isoformat(),
            }
            kind = random.choices(["cash", "bank", "credit"], weights=[6, 2, 3])[0]
            if kind == "credit" and customers:
                body["customer"] = random.choice(customers).pk
            else:
                prices = {product.pk: product.sale_price for product in products}
                total = sum(
                    Decimal(line["quantity"]) * prices[line["product"]] for line in lines
                )
                method = "cash" if kind == "cash" or bank is None else "bank_transfer"
                payment = {"method": method, "amount": str(total)}
                if payment["method"] == "bank_transfer":
                    payment["company_bank_account"] = bank.pk
                    payment["sender_bank_name"] = random.choice(self.text["sender_banks"])
                    payment["reference_last4"] = f"{random.randint(0, 9999):04d}"
                body["payment"] = payment
                if random.random() < 0.5 and customers:
                    body["customer"] = random.choice(customers).pk
            request = factory.post("/api/sales/pos/checkout/", body, format="json")
            force_authenticate(request, user=user)
            response = POSCheckoutView.as_view()(request)
            if response.status_code == 201:
                made += 1
                credit += int(kind == "credit" and bool(customers))
            else:
                failed += 1
                detail = getattr(response, "data", response.status_code)
                self.stderr.write(f"sale refused: {detail}")
        return [f"Sales: {made} invoices ({credit} on credit), {failed} refused"]

    # ------------------------------------------------------------ platform
    def seed_platform(self):
        from website.models import PlatformLead, RegistrationRequest

        leads = 0
        for name, phone, email, channel, message in PLATFORM_LEADS:
            _, created = PlatformLead.objects.get_or_create(
                name=name, defaults={
                    "request_uuid": uuid4(), "phone": phone, "email": email,
                    "preferred_channel": channel, "message": message,
                },
            )
            leads += int(created)
        registrations = 0
        for company_name, contact, email, phone, users, branches in PLATFORM_REGISTRATIONS:
            _, created = RegistrationRequest.objects.get_or_create(
                company_name=company_name, defaults={
                    "request_uuid": uuid4(), "contact_name": contact, "email": email,
                    "phone": phone, "country": "SD", "estimated_users": users,
                    "estimated_branches": branches, "privacy_version": "2026-09",
                    "delivery_mode": RegistrationRequest.SAAS,
                    "message": "بيانات تجريبية لعرض المنصة.",
                },
            )
            registrations += int(created)
        return [f"Platform inbox: {leads} demo leads, {registrations} demo registration requests"]
