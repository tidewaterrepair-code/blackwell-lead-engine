import json
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="pegasus-test-"))
os.environ["PEGASUS_DATA_DIR"] = str(_TMP)
# Run the suite against Postgres with PEGASUS_TEST_DATABASE_URL=postgresql://.../pegasus_test (it is wiped).
os.environ["DATABASE_URL"] = os.environ.get("PEGASUS_TEST_DATABASE_URL") or f"sqlite:///{_TMP / 'test.db'}"
os.environ["SOURCES_FILE"] = str(_TMP / "no-seed-sources.yaml")
os.environ["GEOCODE"] = "0"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_EMAILS"] = "boss@pegasus.test"
for key in ("ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY", "BATCHDATA_API_KEY", "OLLAMA_URL", "SMTP_HOST"):
    os.environ.pop(key, None)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fresh_db():
    from pegasus import db
    from pegasus.api import deps
    from pegasus.notify import OUTBOX

    engine = db.get_engine()
    db.Base.metadata.drop_all(engine)
    db.Base.metadata.create_all(engine)
    deps._hits.clear()
    OUTBOX.clear()
    yield


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()


def mock_client(payload=None, *, content=None, content_type="application/json", handler=None):
    import httpx

    def default(_request):
        if content is not None:
            return httpx.Response(200, content=content, headers={"content-type": content_type})
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler or default))


NORFOLK = {"type": "socrata", "kind": "permit", "domain": "data.norfolk.gov", "dataset": "x", "city": "Norfolk",
           "state": "VA", "county_fips": "51710"}
VB = {"type": "arcgis", "kind": "permit", "url": "https://h/FeatureServer/0", "city": "Virginia Beach", "state": "VA",
      "county_fips": "51810", "date_field": "ApplicationDate",
      "fields": {"external_id": "PermitNumber", "description": "WorkDesc", "address": "FullAddress"}}


def add_source(source_id: str, config: dict):
    from pegasus.db import session_scope
    from pegasus.models import Source

    conf = {k: v for k, v in config.items() if k not in ("type", "kind")}
    with session_scope() as s:
        s.merge(Source(id=source_id, name=source_id, type=config["type"], kind=config.get("kind", "permit"),
                       config=conf, status="active", origin="admin"))


def ingest(source_id: str, config: dict, payload=None, **kw):
    from pegasus.ingest import run_source

    add_source(source_id, config)
    return run_source(source_id, client=mock_client(payload, **kw))


@pytest.fixture
def norfolk_vb(fixture_text):
    """Ingest the Norfolk + Virginia Beach permit fixtures."""
    def run():
        a = ingest("norfolk-permits", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
        b = ingest("vb-permits", VB, json.loads(fixture_text("vb_arcgis.json")))
        return a, b
    return run


def make_org(email: str, trades: list[str], territory: dict | None = None, plan: str | None = None):
    from pegasus.accounts import create_territory, signup
    from pegasus.db import session_scope

    with session_scope() as s:
        user, org = signup(s, email=email, password="supersecret1", name=email.split("@")[0], org_name=None,
                           trades=trades)
        if plan:
            org.plan, org.plan_status = plan, "active"
        if territory:
            create_territory(s, org, **territory)
        return user.id, org.id


HAMPTON_ROADS = {"kind": "radius", "data": {"lat": 36.85, "lng": -76.13, "miles": 35}}
VB_NORFOLK_COUNTIES = {"kind": "county", "data": {"fips": ["51810", "51710"]}}
