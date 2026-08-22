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


EngineKey = tuple[str, str, int, int, float]

_engines: dict[EngineKey, Engine] = {}
_factories: dict[EngineKey, sessionmaker[OrmSession]] = {}


def pool_options_for(settings: Settings) -> PoolOptions:
    pool_sizes = {
        "classroom": 4,
        "general": 5,
        "worker": 2,
        "tile": 1,
        "all": 5,
    }
    return {
        "pool_size": pool_sizes[settings.service_role],
        "max_overflow": 0,
        "pool_timeout": 1.0,
    }


def postgres_timeouts_for(settings: Settings) -> tuple[int, int]:
    statement_timeout_ms = {
        "classroom": 2_000,
        "general": 5_000,
        "worker": 30_000,
        "tile": 5_000,
        "all": 5_000,
    }[settings.service_role]
    lock_timeout_ms = 250 if settings.service_role == "classroom" else 1_000
    return statement_timeout_ms, lock_timeout_ms


def _engine_key(settings: Settings) -> EngineKey:
    options = pool_options_for(settings)
    return (
        settings.database_url,
        settings.service_role,
        options["pool_size"],
        options["max_overflow"],
        options["pool_timeout"],
    )


def engine_for(settings: Settings) -> Engine:
    key = _engine_key(settings)
    if key not in _engines:
        connect_args: dict[str, object] = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        elif settings.database_url.startswith("postgresql"):
            statement_timeout_ms, lock_timeout_ms = postgres_timeouts_for(settings)
            connect_args["options"] = (
                f"-c statement_timeout={statement_timeout_ms} "
                f"-c lock_timeout={lock_timeout_ms}"
            )
        engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            **pool_options_for(settings),
        )
        if engine.dialect.name == "sqlite":
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
