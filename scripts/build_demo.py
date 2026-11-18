"""Erzeugt eine statische Demo des Geräteverleihs für GitHub Pages.

Die echte Anwendung braucht Flask und eine Datenbank. GitHub Pages liefert aber
nur fertige Dateien aus. Dieses Skript startet die App deshalb einmal mit einer
temporären SQLite-Datenbank und den erfundenen Beispieldaten aus seed.py, ruft
alle erreichbaren Seiten über den Flask-Testclient ab und speichert sie als
HTML-Dateien. Formulare werden in der Demo per JavaScript abgefangen, damit klar
ist, dass dort nichts gespeichert wird.

Aufruf:
    python scripts/build_demo.py              (Ausgabe im Ordner demo/)
    python scripts/build_demo.py --out pfad
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import tempfile
from collections import deque
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/Ario-Mi/geraeteverleih"

LINK_PATTERN = re.compile(r'(href|src)="([^"]*)"')
UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
GET_FORM = '<form method="get"'

BANNER = (
    '<div class="demo-banner" role="note">'
    "<strong>Statische Demo</strong> mit erfundenen Beispieldaten. "
    "Änderungen werden nicht gespeichert, die Vollversion läuft lokal mit Flask. "
    f'<a href="{REPO_URL}">Zum Quellcode</a>'
    "</div>"
)

DEMO_CSS = """\
.demo-banner{background:#fff4d6;color:#4a3b00;border-bottom:1px solid #e8d38a;
padding:.6rem 1rem;text-align:center;font-size:.95rem}
.demo-banner a{color:inherit;font-weight:600}
.demo-notice{position:fixed;left:50%;bottom:1.5rem;transform:translateX(-50%);
max-width:min(90vw,32rem);background:#1f2933;color:#fff;padding:.8rem 1.1rem;
border-radius:.5rem;box-shadow:0 6px 24px rgba(0,0,0,.25);z-index:1000;font-size:.95rem}
"""

DEMO_JS = """\
// Fängt Formulare ab: In der statischen Demo gibt es keinen Server, der speichert.
(function () {
  function notice(text) {
    var box = document.querySelector(".demo-notice");
    if (!box) {
      box = document.createElement("div");
      box.className = "demo-notice";
      box.setAttribute("role", "status");
      document.body.appendChild(box);
    }
    box.textContent = text;
    clearTimeout(box.timer);
    box.timer = setTimeout(function () { box.remove(); }, 4500);
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    event.preventDefault();
    var pages = form.dataset.demoPages ? JSON.parse(form.dataset.demoPages) : null;
    if (pages) {
      var query = form.querySelector('[name="q"]');
      var status = form.querySelector('[name="status"]');
      if (query && query.value.trim() !== "") {
        notice("Die Textsuche funktioniert nur in der Vollversion. Der Statusfilter ist in der Demo verfügbar.");
        return;
      }
      if (status && pages[status.value]) {
        window.location.href = pages[status.value];
        return;
      }
    }
    notice("In der statischen Demo wird nichts gespeichert. In der Vollversion wird diese Aktion ausgeführt.");
  });

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-demo-missing]");
    if (link) {
      event.preventDefault();
      notice("Diese Seite ist nur in der Vollversion verfügbar.");
    }
  });
})();
"""


def page_name(url: str) -> str:
    """Wandelt einen internen Pfad samt Query in einen Dateinamen um.

    Beispiele: "/" -> "index.html", "/geraete/3" -> "geraete-3.html",
    "/ausleihen/?status=aktiv" -> "ausleihen--status-aktiv.html".
    Alle Seiten liegen in einem Ordner, dadurch bleiben die Links einfach.
    """
    parts = urlsplit(url)
    name = parts.path.strip("/").replace("/", "-") or "index"
    query = sorted(parse_qsl(parts.query))
    if query:
        name += "--" + "-".join(f"{key}-{value}" for key, value in query)
    return UNSAFE_CHARS.sub("_", name) + ".html"


def is_internal(url: str) -> bool:
    return url.startswith("/") and not url.startswith("//")


def rewrite_links(page: str) -> tuple[str, list[str]]:
    """Ersetzt interne Links durch Dateinamen und gibt die gefundenen Seiten zurück."""
    found: list[str] = []

    def replace(match: re.Match) -> str:
        attribute, raw = match.group(1), match.group(2)
        url = html.unescape(raw)
        if not is_internal(url):
            return match.group(0)
        path, _, fragment = url.partition("#")
        if path.startswith("/static/"):
            target = path.lstrip("/")
        else:
            found.append(path)
            target = page_name(path)
        if fragment:
            target += "#" + fragment
        return f'{attribute}="{html.escape(target, quote=True)}"'

    return LINK_PATTERN.sub(replace, page), found


def crawl(client, seeds: list[str]) -> tuple[dict[str, str], list[str]]:
    """Ruft alle erreichbaren Seiten ab, beginnend bei den Startadressen.

    Gibt die Seiten (Dateiname -> HTML) und die Adressen zurück, die nicht mit
    Status 200 geantwortet haben. Nur GET-Anfragen, es wird nichts verändert.
    """
    pages: dict[str, str] = {}
    sources: dict[str, str] = {}
    skipped: list[str] = []
    queue = deque(seeds)
    seen: set[str] = set()

    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        response = client.get(url)
        if response.status_code != 200 or response.mimetype != "text/html":
            skipped.append(f"{url} (Status {response.status_code})")
            continue

        name = page_name(url)
        if name in sources and sources[name] != url:
            raise RuntimeError(f"{url} und {sources[name]} ergeben denselben Dateinamen {name}")
        sources[name] = url

        page, links = rewrite_links(response.get_data(as_text=True))
        pages[name] = page
        queue.extend(link for link in links if link not in seen)

    return pages, skipped


def mark_missing_links(page: str, existing: set[str]) -> str:
    """Links auf Seiten, die nicht erzeugt wurden, führen in der Demo zu einem Hinweis."""

    def replace(match: re.Match) -> str:
        target = match.group(1)
        if target.split("#")[0] in existing:
            return match.group(0)
        return 'href="#" data-demo-missing'

    return re.sub(r'href="([A-Za-z0-9_-]+\.html(?:#[^"]*)?)"', replace, page)


def add_demo_parts(page: str, filter_pages: dict[str, str]) -> str:
    """Fügt Hinweisbanner, Demo-Styles, Demo-Skript und Filterziele ein."""
    head = '<link rel="stylesheet" href="static/demo.css">\n<script src="static/demo.js" defer></script>\n</head>'
    page = page.replace("</head>", head, 1)
    page = re.sub(r"(<body[^>]*>)", lambda match: match.group(1) + "\n" + BANNER, page, count=1)
    if filter_pages and GET_FORM in page:
        data = html.escape(json.dumps(filter_pages), quote=True)
        page = page.replace(GET_FORM, f'{GET_FORM} data-demo-pages="{data}"', 1)
    return page


def write_site(pages: dict[str, str], out_dir: Path, static_dir: Path,
               filter_pages: dict[str, str] | None = None) -> None:
    """Schreibt alle Seiten und die statischen Dateien in den Ausgabeordner."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(static_dir, out_dir / "static")
    (out_dir / "static" / "demo.css").write_text(DEMO_CSS, encoding="utf-8")
    (out_dir / "static" / "demo.js").write_text(DEMO_JS, encoding="utf-8")
    # Ohne diese Datei würde GitHub Pages Jekyll ausführen; das brauchen wir nicht.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    existing = set(pages)
    for name, page in pages.items():
        page = mark_missing_links(page, existing)
        page = add_demo_parts(page, filter_pages or {})
        (out_dir / name).write_text(page, encoding="utf-8")


def device_filter_pages(status_filters) -> dict[str, str]:
    """Statusfilter der Geräteliste -> passende, vorab erzeugte Seite."""
    return {
        status: page_name("/geraete/" if status == "alle" else f"/geraete/?status={status}")
        for status in status_filters
    }


def build(out_dir: Path) -> None:
    """Baut die Demo mit der echten Anwendung und den Beispieldaten aus seed.py."""
    sys.path.insert(0, str(ROOT))
    from app import create_app, services
    from app.extensions import db
    from app.seed import seed_demo_data

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({
            "TESTING": True,
            "SECRET_KEY": "nur-fuer-den-demo-build",
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(Path(tmp) / 'demo.db').as_posix()}",
        })
        with app.app_context():
            db.create_all()
            seed_demo_data(date.today())
            seeds = ["/", "/geraete/"] + [
                f"/geraete/?status={status}"
                for status in services.DEVICE_STATUS_FILTERS if status != "alle"
            ]
            pages, skipped = crawl(app.test_client(), seeds)
            filters = device_filter_pages(services.DEVICE_STATUS_FILTERS)
            db.session.remove()
            db.engine.dispose()

    write_site(pages, out_dir, ROOT / "app" / "static", filters)
    print(f"Demo erzeugt: {len(pages)} Seiten in {out_dir}")
    for entry in skipped:
        print(f"Übersprungen: {entry}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Statische Demo für GitHub Pages erzeugen")
    parser.add_argument("--out", type=Path, default=ROOT / "demo", help="Ausgabeordner (Standard: demo/)")
    args = parser.parse_args()
    build(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
