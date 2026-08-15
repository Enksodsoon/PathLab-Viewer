from collections.abc import Iterator
from typing import TypedDict

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Base


class PoolOptions(TypedDict):
    pool_size: int
    max_overflow: int
    pool_timeout: float


EngineKey = tuple[str, int, int, float]

_engines: dict[EngineKey, Engine] = {}
_factories: dict[EngineKey, sessionmaker[OrmSession]] = {}


def pool_options_for(settings: Settings) -> PoolOptions:
    return {
        "pool_size": 4 if settings.service_role == "classroom" else 5,
        "max_overflow": 0,
        "pool_timeout": 1.0,
    }


def _engine_key(settings: Settings) -> EngineKey:
    options = pool_options_for(settings)
    return (
        settings.database_url,
        options["pool_size"],
        options["max_overflow"],
        options["pool_timeout"],
    )


def engine_for(settings: Settings) -> Engine:
    key = _engine_key(settings)
    if key not in _engines:
        connect_args = (
            {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        )
        engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            **pool_options_for(settings),
        )
        if settings.database_url.startswith("sqlite"):
            busy_timeout_ms = 1000 if settings.service_role == "classroom" else 5000

            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(connection: object, _: object) -> None:
                cursor = connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
                cursor.close()

        _engines[key] = engine
    return _engines[key]


def session_factory(settings: Settings) -> sessionmaker[OrmSession]:
    key = _engine_key(settings)
    if key not in _factories:
        _factories[key] = sessionmaker(
            bind=engine_for(settings), expire_on_commit=False
        )
    return _factories[key]


def create_schema(settings: Settings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine_for(settings))


def session_dependency(settings: Settings) -> Iterator[OrmSession]:
    with session_factory(settings)() as database:
        yield database
