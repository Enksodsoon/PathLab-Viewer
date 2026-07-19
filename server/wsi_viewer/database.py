from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Base

_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[OrmSession]] = {}


def engine_for(settings: Settings) -> Engine:
    if settings.database_url not in _engines:
        connect_args = (
            {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        )
        engine = create_engine(settings.database_url, connect_args=connect_args)
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(connection: object, _: object) -> None:
                cursor = connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        _engines[settings.database_url] = engine
    return _engines[settings.database_url]


def session_factory(settings: Settings) -> sessionmaker[OrmSession]:
    if settings.database_url not in _factories:
        _factories[settings.database_url] = sessionmaker(
            bind=engine_for(settings), expire_on_commit=False
        )
    return _factories[settings.database_url]


def create_schema(settings: Settings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine_for(settings))


def session_dependency(settings: Settings) -> Iterator[OrmSession]:
    with session_factory(settings)() as database:
        yield database
