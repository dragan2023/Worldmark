"""版本表列宽的方言回归：PostgreSQL 放得下 33 字符的 0007 修订号。"""

from app.db.alembic_support import VERSION_TABLE_DDL, ensure_version_table_width


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Dialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeConnection:
    def __init__(self, dialect: str, *, exists: bool = False, width: int | None = None) -> None:
        self.dialect = _Dialect(dialect)
        self._exists = exists
        self._width = width
        self.statements: list[str] = []
        self.commits = 0

    def exec_driver_sql(self, statement: str) -> _Result:
        self.statements.append(statement)
        if "to_regclass" in statement:
            return _Result("public.alembic_version" if self._exists else None)
        if "information_schema" in statement:
            return _Result(self._width)
        return _Result(None)

    def commit(self) -> None:
        self.commits += 1


def test_postgres_missing_version_table_is_created_wide() -> None:
    connection = _FakeConnection("postgresql", exists=False)

    ensure_version_table_width(connection)

    assert VERSION_TABLE_DDL in connection.statements
    assert "VARCHAR(64)" in VERSION_TABLE_DDL
    assert connection.commits == 1


def test_postgres_narrow_version_table_is_widened() -> None:
    connection = _FakeConnection("postgresql", exists=True, width=32)

    ensure_version_table_width(connection)

    assert any("ALTER COLUMN version_num TYPE VARCHAR(64)" in sql for sql in connection.statements)
    assert connection.commits == 1


def test_postgres_version_table_already_wide_is_left_alone() -> None:
    connection = _FakeConnection("postgresql", exists=True, width=64)

    ensure_version_table_width(connection)

    assert not any("ALTER COLUMN" in sql for sql in connection.statements)
    assert connection.commits == 0


def test_sqlite_is_untouched() -> None:
    connection = _FakeConnection("sqlite", exists=False)

    ensure_version_table_width(connection)

    assert connection.statements == []
    assert connection.commits == 0
