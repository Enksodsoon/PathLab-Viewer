import importlib.util
import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")


@pytest.mark.skipif(POSTGRES_TEST_URL is None, reason="isolated PostgreSQL URL required")
def test_restored_row_comparison_detects_content_changes(monkeypatch, capsys):
    url = make_url(POSTGRES_TEST_URL)
    names = [f"cutover_{kind}_{uuid.uuid4().hex}" for kind in ("source", "restored")]
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    created = []
    try:
        with admin.connect() as connection:
            for name in names:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
                created.append(name)
        for name in names:
            engine = create_engine(url.set(database=name))
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "CREATE TABLE scores (id integer PRIMARY KEY, score numeric, "
                            "payload json, bytes bigint)"
                        )
                    )
                    connection.execute(
                        text(
                            "CREATE TABLE pointers (id integer PRIMARY KEY, "
                            "score_id integer REFERENCES scores(id))"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO scores VALUES "
                            "(1, 1.125, CAST(:payload AS json), 5368709120)"
                        ),
                        {"payload": json.dumps({"synthetic": True})},
                    )
                    connection.execute(text("INSERT INTO pointers VALUES (1, 1)"))
            finally:
                engine.dispose()
        path = Path("deploy/scripts/verify_postgres_database_copy.py")
        spec = importlib.util.spec_from_file_location("verify_postgres_database_copy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setenv(
            "PATHLAB_DATABASE_URL",
            url.set(database=names[0]).render_as_string(
                hide_password=False,
            ),
        )
        monkeypatch.delenv("PATHLAB_DATABASE_PASSWORD_FILE", raising=False)
        monkeypatch.setattr("sys.argv", [str(path), "--restored-database", names[1]])
        module.main()
        receipt = json.loads(capsys.readouterr().out)
        assert receipt == {
            "allRowsAndPrimaryKeysMatch": True,
            "tablesVerified": 2,
            "rowsVerified": 2,
            "foreignKeysVerified": 1,
        }
        engine = create_engine(url.set(database=names[1]))
        try:
            with engine.begin() as connection:
                connection.execute(text("UPDATE scores SET score = 0 WHERE id = 1"))
        finally:
            engine.dispose()
        with pytest.raises(RuntimeError, match="content or foreign keys differ"):
            module.main()
    finally:
        with admin.connect() as connection:
            for name in created:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
