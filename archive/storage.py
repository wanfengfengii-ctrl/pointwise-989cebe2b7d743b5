import sqlite3
from contextlib import contextmanager


def open_archive(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize_archive(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise RuntimeError('initialize the archive outside a publication transaction')
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            body TEXT NOT NULL,
            parent_id INTEGER REFERENCES artifacts(artifact_id),
            frozen_id INTEGER,
            CHECK ((kind = 'calibration' AND parent_id IS NULL AND frozen_id IS NOT NULL AND frozen_id > 0)
                OR (kind = 'switch_report' AND parent_id IS NOT NULL AND frozen_id IS NULL))
        );
        CREATE TABLE IF NOT EXISTS publication_receipts (
            artifact_id INTEGER PRIMARY KEY REFERENCES artifacts(artifact_id),
            receipt_id TEXT NOT NULL UNIQUE
        );
    ''')


@contextmanager
def archive_transaction(connection: sqlite3.Connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
