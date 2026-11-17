from pathlib import Path

from backend.app.store import SQLiteStore


def test_initialize_enables_wal_and_relaxed_sync(tmp_path: Path):
    # The voice WS handler issues ~10+ short writes per turn; WAL + synchronous=NORMAL
    # removes the per-commit fsync that otherwise blocks the event loop. Guard against a
    # regression that drops the pragmas.
    store = SQLiteStore(tmp_path / "t.db")
    store.initialize()
    con = store._connect()
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert con.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        con.close()


def test_store_round_trips_under_wal(tmp_path: Path):
    store = SQLiteStore(tmp_path / "t.db")
    store.initialize()
    session = store.create_session(title="x", source_kind="upload")
    assert store.get_session(session.id) is not None
