from pathlib import Path


def test_migrations_build_the_same_schema_as_the_models(tmp_path, monkeypatch):
    """`pegasus db upgrade` on an empty database must match pegasus.models exactly.

    Fails when a model changes without a migration: run `pegasus db revision -m "..."`.
    """
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    import pegasus
    from pegasus.db import Base

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    here = Path(pegasus.__file__).parent / "migrations"
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
