from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings, get_settings

settings = get_settings()


def connect_args(settings: Settings) -> dict:
    # Supabase's transaction pooler (port 6543) cannot use prepared statements; psycopg would
    # otherwise prepare repeated queries automatically.
    args: dict = {"prepare_threshold": None}
    if settings.database_ca_cert is not None:
        args["sslrootcert"] = str(settings.database_ca_cert)
    return args


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=connect_args(settings),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
    finally:
        session.close()
