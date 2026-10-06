import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="leadengine-test-"))
os.environ["LEADENGINE_DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SOURCES_FILE"] = str(_TMP / "sources.yaml")
os.environ["GEOCODE"] = "0"
os.environ["BASE_LAT"] = "36.85"
os.environ["BASE_LNG"] = "-76.13"
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("OLLAMA_URL", None)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fresh_db():
    from leadengine import db

    engine = db.get_engine()
    db.Base.metadata.drop_all(engine)
    db.Base.metadata.create_all(engine)
    yield


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()
