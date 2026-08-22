from app.database import Database


def test_mysql_prompt_schema_initialization_is_idempotent(
    database: Database,
) -> None:
    database.initialize()

    with database.connect() as connection:
        connection.execute("SHOW COLUMNS FROM prompts")
        columns = {row["Field"] for row in connection.fetchall()}
        connection.execute("SHOW TABLE STATUS LIKE 'prompts'")
        table = connection.fetchone()

    assert table["Engine"] == "InnoDB"
    assert columns == {
        "id",
        "title",
        "prompt",
        "output_format",
        "status",
        "output",
        "error_message",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }
