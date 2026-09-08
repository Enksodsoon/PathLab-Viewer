"""Compare an isolated restored database with its quiesced PostgreSQL source.

Executed inside the pinned backend image. Both transactions are read-only;
only aggregate verification counts leave the container.
"""

import argparse
import json

from sqlalchemy import MetaData, create_engine, inspect, text
from wsi_viewer.config import Settings
from wsi_viewer.database import database_target_for
from wsi_viewer.postgres_migration import _foreign_key_results, _table_evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restored-database", required=True)
    args = parser.parse_args()
    target = database_target_for(Settings())
    source_engine = create_engine(target)
    if source_engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL source required")
    if args.restored_database == source_engine.url.database:
        raise RuntimeError("An independent restored database is required")
    restored_engine = create_engine(source_engine.url.set(database=args.restored_database))
    with source_engine.connect() as source, restored_engine.connect() as restored:
        source.execute(text("SET TRANSACTION READ ONLY"))
        restored.execute(text("SET TRANSACTION READ ONLY"))
        names = set(inspect(source).get_table_names())
        if not names or names != set(inspect(restored).get_table_names()):
            raise RuntimeError("Restored table inventory differs")
        original, copied = MetaData(), MetaData()
        original.reflect(bind=source, only=sorted(names))
        copied.reflect(bind=restored, only=sorted(names))
        tables = [
            _table_evidence(source, restored, original.tables[name], copied.tables[name])
            for name in sorted(names)
        ]
        keys = _foreign_key_results(restored, copied)
        if not all(item["passed"] for item in [*tables, *keys]):
            raise RuntimeError("Restored database content or foreign keys differ")
    print(
        json.dumps(
            {
                "allRowsAndPrimaryKeysMatch": True,
                "tablesVerified": len(tables),
                "rowsVerified": sum(item["sourceCount"] for item in tables),
                "foreignKeysVerified": len(keys),
            }
        )
    )


if __name__ == "__main__":
    main()
