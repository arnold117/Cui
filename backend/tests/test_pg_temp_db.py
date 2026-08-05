from tests.pg_temp_db import temporary_database_url, drop_temporary_database
import pytest

def test_refuses_non_generated_database_names():
    for name in ("postgres", "template0", "template1", "anneal", "cui", "other"):
        with pytest.raises(ValueError):
            temporary_database_url("postgresql+psycopg2://arnold@127.0.0.1:5432/postgres", name)
        with pytest.raises(ValueError):
            drop_temporary_database("postgresql+psycopg2://arnold@127.0.0.1:5432/postgres", name)
