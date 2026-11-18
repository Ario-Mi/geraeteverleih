"""Tests für die statische Demo (scripts/build_demo.py)."""
import re
from datetime import date
from pathlib import Path

from app import services
from app.seed import seed_demo_data
from scripts.build_demo import (
    crawl,
    device_filter_pages,
    page_name,
    rewrite_links,
    write_site,
)


def test_page_name_wandelt_pfade_in_dateinamen_um():
    assert page_name("/") == "index.html"
    assert page_name("/geraete/") == "geraete.html"
    assert page_name("/geraete/3") == "geraete-3.html"
    assert page_name("/ausleihen/?status=aktiv") == "ausleihen--status-aktiv.html"


def test_rewrite_links_ersetzt_nur_interne_links():
    page = (
        '<a href="/geraete/3">Gerät</a>'
        '<a href="https://example.org">extern</a>'
        '<a href="#inhalt">Sprung</a>'
        '<link href="/static/style.css">'
    )
    rewritten, found = rewrite_links(page)
    assert 'href="geraete-3.html"' in rewritten
    assert 'href="https://example.org"' in rewritten
    assert 'href="#inhalt"' in rewritten
    assert 'href="static/style.css"' in rewritten
    assert found == ["/geraete/3"]


def test_demo_enthaelt_alle_hauptseiten_ohne_kaputte_links(app, tmp_path):
    seed_demo_data(date.today())
    seeds = ["/", "/geraete/"] + [
        f"/geraete/?status={status}" for status in services.DEVICE_STATUS_FILTERS if status != "alle"
    ]
    pages, skipped = crawl(app.test_client(), seeds)
    # Keine Seite darf mit einem Serverfehler antworten.
    assert not [entry for entry in skipped if "(Status 5" in entry], skipped

    out = tmp_path / "demo"
    write_site(pages, out, Path(app.static_folder), device_filter_pages(services.DEVICE_STATUS_FILTERS))

    for name in ("index.html", "geraete.html", "personen.html", "ausleihen.html"):
        assert (out / name).exists(), name
    assert (out / "static" / "style.css").exists()

    for file in out.glob("*.html"):
        text = file.read_text(encoding="utf-8")
        assert "Statische Demo" in text
        # Keine absoluten internen Links mehr, sonst wären sie auf GitHub Pages kaputt.
        assert not re.search(r'(href|src)="/(?!/)', text), file.name
        for target in re.findall(r'href="([A-Za-z0-9_-]+\.html)', text):
            assert (out / target).exists(), f"{file.name} verweist auf fehlende Seite {target}"

    assert "überfällig" in (out / "index.html").read_text(encoding="utf-8")
