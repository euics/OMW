import pytest

from app.core.config import get_settings
from app.database import Database


@pytest.fixture
def database() -> Database:
    settings = get_settings()
    database = Database(
        host=settings.database_host,
        port=settings.database_port,
        name=settings.database_name,
        user=settings.database_user,
        password=settings.database_password.get_secret_value(),
    )
    database.initialize()

    with database.connect() as connection:
        connection.execute("DELETE FROM prompts")

    yield database

    with database.connect() as connection:
        connection.execute("DELETE FROM prompts")