import csv
import json
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.conftest import HAMPTON_ROADS, NORFOLK, ingest, make_org

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    from pegasus.web.app import create_app

    with TestClient(create_app()) as c:
        yield c


# ------------------------------------------------------------------ ads, calendar, banners

def test_campaign_spec_is_valid_and_exports(tmp_path):
    from pegasus.marketing.ads import export, validate

    spec = yaml.safe_load((ROOT / "marketing/ads/campaigns.yaml").read_text())
    assert validate(spec) == []
    paths = export(ROOT / "marketing/ads/campaigns.yaml", tmp_path)
    meta = list(csv.DictReader(paths["meta"].open()))
    assert len(meta) == sum(len(a["ads"]) for c in spec["meta"] for a in c["ad_sets"])
    assert all(r["Campaign Status"] == "PAUSED" and "utm_source=meta" in r["Link"] for r in meta)
    google = list(csv.DictReader(paths["google"].open()))
    ads = [r for r in google if r["Ad Type"] == "Responsive search ad"]
    assert ads and all(len(r["Headline 1"]) <= 30 and "utm_medium=cpc" in r["Final URL"] for r in ads)
    assert any(r["Criterion Type"] == "Campaign Negative Phrase" for r in google)


def test_validate_flags_overlong_copy():
    from pegasus.marketing.ads import validate

    spec = {"google": [{"ad_groups": [{"name": "g", "headlines": ["x" * 31, "a", "b"], "descriptions": ["d", "e"]}]}],
            "meta": [{"ad_sets": [{"ads": [{"name": "m", "headline": "h", "primary": "p"}]}]}]}
    problems = validate(spec)
    assert any("headline over 30" in p for p in problems) and any("needs a video or image" in p for p in problems)


def test_calendar_covers_30_days():
    from pegasus.marketing.cli import check_calendar

    assert check_calendar(ROOT / "marketing/content/calendar.csv") == []


@pytest.mark.parametrize("size,mode", [("728x90", "strip"), ("160x600", "tower"), ("300x250", "small"),
                                       ("1200x628", "wide"), ("1080x1080", "square"), ("1080x1920", "tall")])
def test_banner_layouts(size, mode):
    from pegasus.marketing.banners import banner_html, layout, parse_size

    assert layout(*parse_size(size)) == mode
    html = banner_html({"id": "t", "layout": "audience", "kicker": "K", "headline": ["See the <job>", "*Call first.*"],
                        "sub": "S", "cta": "Go", "bullets": [["home", "New builds"]]}, size)
    assert "&lt;job&gt;" in html and '<span class="gold">Call first.</span>' in html and "@font-face" in html
    assert "data:image/svg+xml;base64," in html  # no plate on disk: code-drawn scene


def test_short_headline_and_cta_on_small_sizes():
    from pegasus.marketing.banners import banner_html

    b = {"id": "t", "headline": ["A very long headline", "*goes here*"], "short": ["Short one"],
         "cta": "Get construction leads", "cta_short": "Get leads"}
    small = banner_html(b, "300x250")
    assert "Short one" in small and "Get leads" in small and "very long" not in small
    assert "very long" in banner_html(b, "1080x1080")


def test_plate_photo_is_used_when_present(tmp_path, monkeypatch):
    import base64

    from pegasus.marketing import banners

    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg==")
    (tmp_path / "city.png").write_bytes(png)
    monkeypatch.setattr(banners, "PLATES", tmp_path)
    banners._data_uri.cache_clear()
    html = banners.banner_html({"id": "t", "headline": ["Hi"], "plate": "city", "focus": "70% 40%"}, "1080x1080")
    assert "data:image/png;base64," in html and "70% 40%" in html


def test_every_banner_in_copy_renders_to_html():
    from html import escape

    from pegasus.marketing.banners import banner_html, load_copy

    data = load_copy(ROOT / "marketing/banners/copy.yaml")
    assert len([b for b in data["banners"] if b["id"] != "og-image"]) == 13
    for b in data["banners"]:
        for size in b.get("sizes", data["sizes"]):
            html = banner_html(b, size)
            lines = b.get("short") if size in ("300x250", "728x90", "160x600") and b.get("short") else b["headline"]
            assert escape(lines[0].replace("*", "")) in html, (b["id"], size)


def test_brand_pack_assets_are_in_place():
    """The app, site, emails and ads all use artwork cut from marketing/brand/source."""
    brand = ROOT / "pegasus/web/static/brand"
    for name in ("logo.png", "logo-mark.png", "logo-wordmark.png", "splash.png", "email-wordmark.png",
                 "pegasus-32.png", "pegasus-192.png", "pegasus-512.png", "apple-touch-icon.png"):
        assert (brand / name).stat().st_size > 500, name
    assert (ROOT / "marketing/brand/source/logo-primary.png").exists()
    assert (ROOT / "marketing/brand/source/brand-pack.webp").exists()


def test_brand_pack_importer(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    from pegasus.marketing import brand_pack

    monkeypatch.setattr(brand_pack, "STATIC", tmp_path / "static")
    monkeypatch.setattr(brand_pack, "PACK_OUT", tmp_path / "pack")
    written = {p.name for p in brand_pack.main()}
    assert {"logo.png", "logo-mark.png", "splash.png", "pegasus-512.png", "website-hero.png"} <= written
    logo = Image.open(tmp_path / "static" / "logo.png")
    assert logo.mode == "RGBA" and logo.getpixel((0, 0))[3] == 0  # black background keyed out
    assert Image.open(tmp_path / "static" / "pegasus-512.png").size == (512, 512)


def test_banners_embed_brand_artwork():
    from pegasus.marketing.banners import banner_html

    square = banner_html({"id": "t", "headline": ["Hi"], "cta": "Go"}, "1080x1080")
    assert 'class="lockup"' in square and square.count("data:image/png;base64,") >= 2
    hero = banner_html({"id": "t", "layout": "hero", "headline": ["Hi"], "tagline": ["A", "*B*"]}, "1080x1080")
    assert "data:image/png;base64," in hero


# ------------------------------------------------------------------ weekly data posts

def test_weekly_posts_from_live_data(tmp_path, fixture_text):
    from pegasus.marketing.weekly import city_stats, compose, write_weekly

    ingest("nor", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
    stats = city_stats("Norfolk", "VA")
    assert stats["count"] > 0 and stats["top_tags"]
    post = compose(stats)
    assert f"{stats['count']} new projects" in post["caption"] and "/leads/va/norfolk" in post["url"]
    written = write_weekly([("Norfolk", "VA"), ("Nowhere", "VA")], tmp_path)
    assert [p.name for p in written] == ["norfolk.md"]


# ------------------------------------------------------------------ lifecycle email

def _outbox():
    from pegasus.notify import OUTBOX

    return OUTBOX


def _run(days: float = 0):
    from pegasus.db import session_scope, utcnow
    from pegasus.lifecycle import run_lifecycle

    with session_scope() as s:
        return run_lifecycle(s, now=utcnow() + timedelta(days=days))


def test_sequences_are_well_formed():
    from pegasus.lifecycle import sequences

    seqs = sequences()
    assert {"waitlist", "onboarding", "trial", "winback", "launch"} <= set(seqs)
    ids = [e["id"] for q in seqs.values() for e in q["emails"]]
    assert len(ids) == len(set(ids)) == 20
    for q in seqs.values():
        for e in q["emails"]:
            assert e["subject"] and e["body"] and len(e["cta"]) == 2


def test_onboarding_sends_once_with_unsubscribe():
    _outbox().clear()
    make_org("new@pegasus.test", ["deck_builder"])
    assert _run() == 1
    msg = _outbox()[-1]
    assert msg["subject"].startswith("Welcome to Pegasus") and "Unsubscribe" in msg["html"]
    assert msg["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert _run() == 0  # never twice


def test_skip_if_and_backlog_window():
    _outbox().clear()
    make_org("blank@pegasus.test", ["deck_builder"])
    make_org("ready@pegasus.test", ["deck_builder"], territory=HAMPTON_ROADS)
    _run(1)  # day 1: only the account without an area gets the "draw your area" nudge
    area = [m["to"] for m in _outbox() if m["subject"] == "Your area is still blank"]
    assert area == ["blank@pegasus.test"]
    _outbox().clear()
    _run(30)  # long past every onboarding email's window: nothing old is blasted
    assert not [m for m in _outbox() if "Welcome" in m["subject"]]


def test_trial_sequence_stops_when_paid():
    from pegasus.db import session_scope
    from pegasus.models import Org

    _outbox().clear()
    _, paid_id = make_org("paid@pegasus.test", ["roofer"])
    make_org("trial@pegasus.test", ["roofer"])
    with session_scope() as s:
        org = s.get(Org, paid_id)
        org.stripe_subscription_id, org.plan_status = "sub_1", "active"
    _run(11)  # trial is 14 days: day 11 = three days before it ends
    got = [m["to"] for m in _outbox() if m["subject"] == "Your trial ends in 3 days"]
    assert got == ["trial@pegasus.test"]


def test_realty_only_email_and_winback():
    from pegasus.billing import apply_event
    from pegasus.db import session_scope
    from pegasus.models import Org

    _outbox().clear()
    _, org_id = make_org("agent@pegasus.test", ["real_estate_agent"])
    with session_scope() as s:
        org = s.get(Org, org_id)
        org.mode, org.stripe_customer_id, org.stripe_subscription_id = "realestate", "cus_1", "sub_9"
    _run(8)
    assert any(m["subject"] == "Run a deal in five seconds" for m in _outbox())
    with session_scope() as s:
        apply_event(s, {"id": "evt_1", "type": "customer.subscription.deleted",
                        "data": {"object": {"id": "sub_9", "customer": "cus_1"}}})
        assert s.get(Org, org_id).settings.get("canceled_at")
    _run(3)
    assert any(m["subject"] == "Sorry to see you go" for m in _outbox())


def test_waitlist_nurture_and_unsubscribe(client):
    from pegasus.db import session_scope
    from pegasus.lifecycle import unsubscribe_url
    from pegasus.models import EmailSuppression

    _outbox().clear()
    assert client.post("/api/waitlist", json={"email": "w@pegasus.test", "name": "Wes Lee", "city": "Norfolk"}
                       ).status_code in (200, 201)
    _run()
    first = [m for m in _outbox() if m["to"] == "w@pegasus.test"]
    assert len(first) == 1 and "Hi Wes," in first[0]["text"] and "founding seats left" in first[0]["text"]

    path = unsubscribe_url("w@pegasus.test").split("://", 1)[1].split("/", 1)[1]
    r = client.get("/" + path)
    assert r.status_code == 200 and "unsubscribed" in r.text
    with session_scope() as s:
        assert s.get(EmailSuppression, "w@pegasus.test")
    _outbox().clear()
    _run(2)
    assert not [m for m in _outbox() if m["to"] == "w@pegasus.test"]
    assert "didn't work" in client.get("/email/unsubscribe?t=forged").text


def test_waitlist_stops_once_they_sign_up(client):
    _outbox().clear()
    client.post("/api/waitlist", json={"email": "conv@pegasus.test"})
    make_org("conv@pegasus.test", ["painter"])
    _run(2)
    assert not [m for m in _outbox() if m["subject"] == "One permit, 14 trades"]


def test_leads_index_lists_cities(client, fixture_text):
    ingest("nor", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
    r = client.get("/leads")
    assert r.status_code == 200 and "/leads/va/norfolk" in r.text
    assert "/leads</loc>" in client.get("/sitemap.xml").text
