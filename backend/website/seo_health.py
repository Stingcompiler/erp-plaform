"""The SEO health check behind the platform team's «صحة SEO» tab.

Read-only: it looks at what search engines are actually given and reports
what is missing or off, so the team knows which override to write next.

- Export pages: every public marketing page in frontend/out (Arabic at the
  root, English under /en/), parsed with the standard library's HTML parser,
  never rendered. The signed-in app is skipped: anything robots.txt
  disallows or that carries a noindex robots meta, unless the sitemap lists
  it (then the noindex is itself the problem). Each page's title and
  description are judged *after* the team's override, the way core.frontend
  serves them.
- Sitemap: out/sitemap.xml against the export, both ways, and robots.txt
  naming both sitemaps (the marketing one and Django's sitemap-sites.xml).
- Company pages (/s/<slug>/): published sites missing what makes a useful
  result, kept out of the index, or not listed in the directory.
- Settings: the verification tags, the default share image and the extra
  robots.txt lines.
- Redirects (website.redirects): an old path still listed in a sitemap, and
  a new address on this site with no page behind it.

Every finding is a code plus plain params; the page words them in either
language. The whole report is cached for five minutes (CACHE_SECONDS);
saving an SEO setting or override clears it with the served-page cache
(website.seo.invalidate_seo_cache).
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.public_media import stored_public_url
from core.seo_inject import public_path_and_language

CACHE_KEY = "seo:health"
CACHE_SECONDS = 300

ERROR = "error"
WARN = "warn"
OK = "ok"
SEVERITIES = (ERROR, WARN, OK)
_RANK = {OK: 0, WARN: 1, ERROR: 2}

TITLE_MIN, TITLE_MAX = 15, 60
DESCRIPTION_MIN, DESCRIPTION_MAX = 50, 160
LANGUAGES = ("ar", "en")

# Directives robots.txt readers understand; anything else in the team's
# extra lines is probably a typo that crawlers will silently ignore.
ROBOTS_DIRECTIVES = {
    "user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host", "clean-param",
}
_NOINDEX = re.compile(r"\bnoindex\b", re.IGNORECASE)


def site_origin():
    return f"https://{settings.VEZANO_CANONICAL_HOST}"


def worst(severities):
    return max(severities, key=_RANK.__getitem__, default=OK)


def issue(code, severity, **params):
    return {"code": code, "severity": severity, "params": params}


def _with_severity(row):
    row["severity"] = worst(item["severity"] for item in row["issues"])
    return row


# --- Parsing ---------------------------------------------------------------


class PageFacts(HTMLParser):
    """The few facts of one exported page the checks need."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.head_done = False
        self.title = None
        self.metas = {}
        self.canonical = None
        self.hreflang = {}
        self.h1 = 0
        self.json_ld = []
        self._capture = None
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = {name.lower(): (value or "") for name, value in attrs}
        if tag == "head" and not self.head_done:
            self.in_head = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "title" and self.in_head and self.title is None:
            self._start("title")
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._start("ld")
        elif tag == "meta" and self.in_head:
            key = attrs.get("name") or attrs.get("property")
            if key and key.lower() not in self.metas:
                self.metas[key.lower()] = attrs.get("content", "")
        elif tag == "link" and self.in_head:
            rel = attrs.get("rel", "").lower().split()
            if "canonical" in rel and self.canonical is None:
                self.canonical = attrs.get("href", "")
            elif "alternate" in rel and attrs.get("hreflang"):
                self.hreflang[attrs["hreflang"].lower()] = attrs.get("href", "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
            self.head_done = True
        elif tag == "title" and self._capture == "title":
            self.title = " ".join("".join(self._buffer).split())
            self._capture = None
        elif tag == "script" and self._capture == "ld":
            self.json_ld.append("".join(self._buffer))
            self._capture = None

    def handle_data(self, data):
        if self._capture:
            self._buffer.append(data)

    def _start(self, kind):
        self._capture = kind
        self._buffer = []


def parse_page(text):
    facts = PageFacts()
    facts.feed(text)
    facts.close()
    return facts


def robots_disallows(text):
    """Every Disallow prefix in a robots.txt, in order."""
    found = []
    for line in (text or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "disallow" and value.strip():
            found.append(value.strip())
    return found


def robots_sitemaps(text):
    found = []
    for line in (text or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            found.append(value.strip())
    return found


def sitemap_paths(text, origin):
    """URL paths listed in a sitemap, plus the <loc>s that are off-host."""
    root = ElementTree.fromstring(text)
    paths, foreign = [], []
    for loc in root.iter():
        if not loc.tag.endswith("}loc") and loc.tag != "loc":
            continue
        url = (loc.text or "").strip()
        if url.startswith(origin + "/"):
            paths.append(url[len(origin):])
        elif url:
            foreign.append(url)
    return paths, foreign


def url_path_of(relative):
    """'/en/pricing/' for 'en/pricing/index.html'; '/' for 'index.html'."""
    parts = Path(relative).parts
    if parts[-1] == "index.html":
        parts = parts[:-1]
    else:
        parts = parts[:-1] + (parts[-1][: -len(".html")],)
    return "/" + "".join(f"{part}/" for part in parts)


def _skipped_file(relative):
    first = Path(relative).parts[0]
    return first.startswith("_") or first == "404" or relative == "404.html"


# --- Checks ----------------------------------------------------------------


def _length_issues(kind, text, low, high):
    if not text:
        return [issue(f"{kind}_missing", ERROR)]
    length = len(text)
    if length < low:
        return [issue(f"{kind}_short", WARN, length=length, min=low)]
    if length > high:
        return [issue(f"{kind}_long", WARN, length=length, max=high)]
    return []


def page_issues(facts, url_path, *, origin, override=None, default_og_image=False):
    """Findings for one parsed page, with the override applied the way
    core.seo_inject applies it. Returns (effective values, issues)."""
    override = override or {}
    title = override.get("title") or facts.title or ""
    description = override.get("description") or facts.metas.get("description", "")
    canonical = override.get("canonical") or facts.canonical or ""
    issues = []
    issues += _length_issues("title", title, TITLE_MIN, TITLE_MAX)
    issues += _length_issues("description", description, DESCRIPTION_MIN, DESCRIPTION_MAX)

    expected = origin + url_path
    if not canonical:
        issues.append(issue("canonical_missing", ERROR))
    elif not (canonical == origin or canonical.startswith(origin + "/")):
        issues.append(issue("canonical_host", ERROR, canonical=canonical, origin=origin))
    elif canonical != expected:
        issues.append(issue("canonical_other", WARN, canonical=canonical, expected=expected))

    missing = [code for code in LANGUAGES if code not in facts.hreflang]
    if missing:
        issues.append(issue("hreflang_missing", ERROR, languages=missing))
    else:
        off = [
            code for code in LANGUAGES
            if not facts.hreflang[code].startswith(origin + "/")
        ]
        if off:
            issues.append(issue("hreflang_host", ERROR, languages=off))

    if facts.h1 == 0:
        issues.append(issue("h1_missing", ERROR))
    elif facts.h1 > 1:
        issues.append(issue("h1_multiple", WARN, count=facts.h1))

    if not facts.metas.get("og:image") and not default_og_image:
        issues.append(issue("og_image_missing", WARN))

    if not facts.json_ld:
        issues.append(issue("jsonld_missing", WARN))
    else:
        bad = 0
        for block in facts.json_ld:
            try:
                json.loads(block)
            except ValueError:
                bad += 1
        if bad:
            issues.append(issue("jsonld_invalid", ERROR, count=bad, total=len(facts.json_ld)))

    if override.get("noindex"):
        issues.append(issue("override_noindex", WARN))
    elif _NOINDEX.search(facts.metas.get("robots", "")):
        issues.append(issue("noindex_in_sitemap", ERROR))

    effective = {
        "title": title,
        "title_length": len(title),
        "description": description,
        "description_length": len(description),
        "canonical": canonical,
        "own_title": facts.title or "",
        "own_description": facts.metas.get("description", ""),
        "h1_count": facts.h1,
        "json_ld_count": len(facts.json_ld),
        "hreflang": sorted(facts.hreflang),
    }
    return effective, issues


def _override_rows():
    from website.models import SeoPageOverride

    return {(row.path, row.language): row for row in SeoPageOverride.objects.all()}


def _override_for(rows, path, language):
    row = rows.get((path, language)) or rows.get((path, "both"))
    if row is None:
        return None
    return {
        "id": row.pk,
        "path": row.path,
        "language": row.language,
        "title": row.title.strip(),
        "description": row.description.strip(),
        "noindex": row.noindex,
        "canonical": row.canonical.strip(),
    }


def check_export(dist, overrides, *, default_og_image, origin):
    """(pages, sitemap section) for the static export at `dist`."""
    dist = Path(dist)
    sitemap = {
        "available": False, "url_count": 0, "missing_from_sitemap": [],
        "missing_from_export": [], "foreign_urls": [], "robots_sitemaps": [], "issues": [],
    }
    if not (dist / "index.html").is_file():
        sitemap["issues"].append(issue("export_missing", ERROR))
        return [], _with_severity(sitemap)

    robots_file = dist / "robots.txt"
    robots_text = robots_file.read_text(encoding="utf-8") if robots_file.is_file() else ""
    disallowed = robots_disallows(robots_text)
    sitemap["robots_sitemaps"] = robots_sitemaps(robots_text)
    if not robots_text:
        sitemap["issues"].append(issue("robots_missing", ERROR))
    for name in ("sitemap.xml", "sitemap-sites.xml"):
        if robots_text and f"{origin}/{name}" not in sitemap["robots_sitemaps"]:
            sitemap["issues"].append(issue("robots_sitemap_missing", WARN, sitemap=name))

    listed = []
    sitemap_file = dist / "sitemap.xml"
    if sitemap_file.is_file():
        try:
            listed, foreign = sitemap_paths(sitemap_file.read_text(encoding="utf-8"), origin)
            sitemap["available"] = True
            sitemap["foreign_urls"] = foreign
            if foreign:
                sitemap["issues"].append(issue("sitemap_foreign", ERROR, count=len(foreign)))
        except ElementTree.ParseError:
            sitemap["issues"].append(issue("sitemap_invalid", ERROR))
    else:
        sitemap["issues"].append(issue("sitemap_missing", ERROR))
    in_sitemap = set(listed)
    sitemap["url_count"] = len(listed)

    files = {}
    for file in sorted(dist.rglob("*.html")):
        relative = file.relative_to(dist).as_posix()
        if not _skipped_file(relative):
            files[url_path_of(relative)] = (relative, file)

    pages, indexable = [], set()
    for url_path, (relative, file) in files.items():
        if url_path not in in_sitemap and any(url_path.startswith(p) for p in disallowed):
            continue
        facts = parse_page(file.read_text(encoding="utf-8"))
        if url_path not in in_sitemap and _NOINDEX.search(facts.metas.get("robots", "")):
            continue
        indexable.add(url_path)
        path, language = public_path_and_language(url_path)
        override = _override_for(overrides, path, language)
        effective, issues = page_issues(
            facts, url_path, origin=origin, override=override,
            default_og_image=default_og_image,
        )
        if sitemap["available"] and url_path not in in_sitemap and not (
            override and override["noindex"]
        ):
            issues.append(issue("not_in_sitemap", WARN))
        pages.append(_with_severity({
            "path": path,
            "language": language,
            "url_path": url_path,
            "url": origin + url_path,
            "file": relative,
            "in_sitemap": url_path in in_sitemap,
            "override": override,
            **effective,
            "issues": issues,
        }))

    if sitemap["available"]:
        sitemap["missing_from_sitemap"] = sorted(indexable - in_sitemap)
        sitemap["missing_from_export"] = sorted(in_sitemap - set(files))
        if sitemap["missing_from_sitemap"]:
            sitemap["issues"].append(issue(
                "pages_not_in_sitemap", WARN, count=len(sitemap["missing_from_sitemap"])
            ))
        if sitemap["missing_from_export"]:
            sitemap["issues"].append(issue(
                "sitemap_dead_urls", ERROR, count=len(sitemap["missing_from_export"])
            ))
    return pages, _with_severity(sitemap)


def check_companies(overrides, origin):
    """Published company pages and what keeps each from being a good result."""
    from website.models import Website, service_lines

    noindexed = {
        path for (path, _language), row in overrides.items() if row.noindex
    }
    rows = []
    sites = (
        Website.objects.filter(is_published=True, company__is_active=True)
        .select_related("company")
        .order_by("business_name", "company__name")
    )
    for site in sites:
        slug = site.company.slug
        path = f"/s/{slug}"
        missing = []
        if not (stored_public_url(site.logo_image) or site.logo_url):
            missing.append("logo")
        if not (site.tagline.strip() or site.about_text.strip()):
            missing.append("description")
        if not stored_public_url(site.cover_image):
            missing.append("cover")
        if not (site.contact_phone.strip() or site.contact_email.strip()):
            missing.append("contact")
        if not service_lines(site.services):
            missing.append("services")
        issues = [issue(f"company_{field}_missing", WARN) for field in missing]
        noindex = path in noindexed
        if noindex:
            issues.append(issue("company_noindex", WARN))
        if not site.list_in_directory:
            issues.append(issue("company_not_listed", WARN))
        rows.append(_with_severity({
            "company_id": site.company_id,
            "name": site.business_name or site.company.name,
            "slug": slug,
            "path": path,
            "url": f"{origin}{path}/",
            "is_demo": site.company.is_demo,
            "listed": site.list_in_directory,
            "noindex": noindex,
            "in_directory": site.list_in_directory and not noindex,
            "missing": missing,
            "issues": issues,
        }))
    return rows


def check_settings(settings_row, overrides, sitemap_paths_listed=()):
    """Site-wide checks, one row each."""
    google = (settings_row.google_site_verification.strip() if settings_row else "")
    bing = (settings_row.bing_site_verification.strip() if settings_row else "")
    image = stored_public_url(settings_row.default_og_image) if settings_row else ""
    extra = settings_row.robots_extra if settings_row else ""
    checks = [
        {"code": "google_verification", "issues": [] if google else [
            issue("google_verification_missing", WARN)
        ]},
        {"code": "bing_verification", "issues": [] if bing else [
            issue("bing_verification_missing", WARN)
        ]},
        {"code": "default_og_image", "issues": [] if image else [
            issue("default_og_image_missing", WARN)
        ]},
        {"code": "robots_extra", "issues": robots_extra_issues(extra, sitemap_paths_listed)},
    ]
    directory = overrides.get(("/s", "ar")) or overrides.get(("/s", "both"))
    checks.append({"code": "directory", "issues": [
        issue("directory_noindex", ERROR)
    ] if directory is not None and directory.noindex else []})
    return [_with_severity(check) for check in checks]


def robots_extra_issues(extra, listed_paths=()):
    issues = []
    for number, raw in enumerate((extra or "").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, colon, value = line.partition(":")
        key = key.strip().lower()
        if not colon or key not in ROBOTS_DIRECTIVES:
            issues.append(issue("robots_extra_unknown", WARN, line=number, text=raw.strip()))
            continue
        value = value.strip()
        if key == "disallow" and value == "/":
            issues.append(issue("robots_extra_blocks_all", ERROR, line=number))
        elif key == "disallow" and value:
            blocked = [path for path in listed_paths if path.startswith(value)]
            if blocked:
                issues.append(issue(
                    "robots_extra_blocks_pages", ERROR, line=number, count=len(blocked),
                    example=blocked[0],
                ))
    return issues


# Paths Django serves itself (not the export): a redirect landing there is
# not judged against frontend/out.
_NOT_IN_EXPORT = ("/api", "/admin", "/static", "/media", "/sitemap-sites.xml")


def _export_serves(dist, key):
    """Whether the export at `dist` has a file for the lookup key `key`,
    the way core.frontend looks one up."""
    relative = key.strip("/")
    if ".." in relative.split("/"):
        return False
    if not relative:
        return (dist / "index.html").is_file()
    base = dist / relative
    return any(
        candidate.is_file()
        for candidate in (base, base / "index.html", base.with_name(f"{base.name}.html"))
    )


def check_redirects(dist, origin):
    """Active redirects whose old path is still listed in a sitemap, or
    whose new address on this site has no page."""
    from website.models import SeoRedirect, Website
    from website.redirects import request_key, target_key

    dist = Path(dist)
    export = (dist / "index.html").is_file()
    listed = set()
    sitemap_file = dist / "sitemap.xml"
    if sitemap_file.is_file():
        try:
            paths, _foreign = sitemap_paths(sitemap_file.read_text(encoding="utf-8"), origin)
            listed = {request_key(path) for path in paths}
        except ElementTree.ParseError:
            pass
    published = {
        slug.lower(): listed_flag
        for slug, listed_flag in Website.objects.filter(
            is_published=True, company__is_active=True
        ).values_list("company__slug", "list_in_directory")
    }
    rows = []
    for row in SeoRedirect.objects.filter(is_active=True).order_by("source_path"):
        issues = []
        source = row.source_path
        parts = source.split("/")
        if source in listed:
            issues.append(issue("redirect_in_sitemap", WARN, sitemap="sitemap.xml"))
        elif len(parts) == 3 and parts[1] == "s" and published.get(parts[2]):
            issues.append(issue("redirect_in_sitemap", WARN, sitemap="sitemap-sites.xml"))
        landing, _problem = target_key(row.target, allow_external=True)
        if landing is not None and not any(
            landing == prefix or landing.startswith(prefix + "/") for prefix in _NOT_IN_EXPORT
        ):
            target_parts = landing.split("/")
            if landing == "/s":
                served = True
            elif len(target_parts) >= 3 and target_parts[1] == "s":
                served = target_parts[2] in published
            else:
                served = not export or _export_serves(dist, landing)
            if not served:
                issues.append(issue("redirect_target_missing", ERROR, target=row.target))
        rows.append(_with_severity({
            "id": row.pk,
            "source_path": source,
            "target": row.target,
            "status_code": row.status_code,
            "url": origin + source + ("/" if source != "/" else ""),
            "issues": issues,
        }))
    return rows


def _summary(*groups):
    counts = dict.fromkeys(SEVERITIES, 0)
    codes = {}
    for group in groups:
        for row in group:
            counts[row["severity"]] += 1
            for item in row["issues"]:
                key = (item["code"], item["severity"])
                codes[key] = codes.get(key, 0) + 1
    top = sorted(codes.items(), key=lambda kv: (-_RANK[kv[0][1]], -kv[1], kv[0][0]))
    return {
        **counts,
        "total": sum(counts.values()),
        "issues": [
            {"code": code, "severity": severity, "count": count}
            for (code, severity), count in top
        ],
    }


def build_report(dist=None):
    """The whole report, computed now (no cache)."""
    from core import frontend
    from website.models import SeoSettings

    dist = frontend.FRONTEND_DIST if dist is None else dist
    origin = site_origin()
    overrides = _override_rows()
    settings_row = SeoSettings.objects.filter(pk=SeoSettings.SINGLETON_PK).first()
    default_og_image = bool(settings_row and stored_public_url(settings_row.default_og_image))
    pages, sitemap = check_export(
        dist, overrides, default_og_image=default_og_image, origin=origin
    )
    companies = check_companies(overrides, origin)
    checks = check_settings(
        settings_row, overrides, [page["url_path"] for page in pages if page["in_sitemap"]]
    )
    redirects = check_redirects(dist, origin)
    return {
        "generated_at": timezone.now().isoformat(),
        "origin": origin,
        "limits": {
            "title": [TITLE_MIN, TITLE_MAX],
            "description": [DESCRIPTION_MIN, DESCRIPTION_MAX],
        },
        "summary": _summary(pages, [sitemap], companies, checks, redirects),
        "pages": pages,
        "sitemap": sitemap,
        "companies": companies,
        "settings": checks,
        "redirects": redirects,
    }


def health_report(refresh=False):
    """The cached report; `refresh` recomputes it first."""
    report = None if refresh else cache.get(CACHE_KEY)
    cached = report is not None
    if report is None:
        report = build_report()
        cache.set(CACHE_KEY, report, CACHE_SECONDS)
    return {**report, "cached": cached}


def invalidate_health_cache():
    cache.delete(CACHE_KEY)
