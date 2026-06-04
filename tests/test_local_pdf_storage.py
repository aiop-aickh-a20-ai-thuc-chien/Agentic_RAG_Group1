from agentic_rag.integrations.local_pdf.storage import _psycopg_connection_string


def test_psycopg_connection_string_accepts_sqlalchemy_psycopg_scheme() -> None:
    assert (
        _psycopg_connection_string("postgresql+psycopg://user:pass@example.com/db")
        == "postgresql://user:pass@example.com/db"
    )
