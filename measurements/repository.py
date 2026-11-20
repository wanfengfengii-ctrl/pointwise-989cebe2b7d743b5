import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager

from measurements.manifest import FrozenManifest
from measurements.revisions import ReadingRevision
from protocol.levels import require_identifier
from protocol.rationals import encode_rational, parse_rational
from protocol.registry import get_rule, initialize_rules


def _is_id(value) -> bool:
    return type(value) is int and 1 <= value < 2**63


def _decode_reading(row: sqlite3.Row) -> ReadingRevision:
    return ReadingRevision(
        revision_id=row['revision_id'],
        batch_id=row['batch_id'],
        protocol_version=row['protocol_version'],
        original_id=row['original_id'],
        level=row['level'],
        value=parse_rational(row['reading_value']),
        weight=int(row['weight_hex'], 16),
        prior_revision_id=row['prior_revision_id'],
    )


class MeasurementRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys = ON')

    @classmethod
    def open(cls, path):
        return cls(sqlite3.connect(path, isolation_level=None))

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        if self.connection.in_transaction:
            raise RuntimeError('initialize the source outside a work transaction')
        initialize_rules(self.connection)
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                protocol_version INTEGER NOT NULL REFERENCES protocol_rules(version_id)
            );
            CREATE TABLE IF NOT EXISTS reading_revisions (
                revision_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                protocol_version INTEGER NOT NULL REFERENCES protocol_rules(version_id),
                original_id TEXT NOT NULL,
                level TEXT NOT NULL,
                reading_value TEXT NOT NULL,
                weight_hex TEXT NOT NULL,
                prior_revision_id INTEGER REFERENCES reading_revisions(revision_id)
            );
            CREATE TABLE IF NOT EXISTS reading_heads (
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                original_id TEXT NOT NULL,
                revision_id INTEGER NOT NULL UNIQUE REFERENCES reading_revisions(revision_id),
                PRIMARY KEY (batch_id, original_id)
            );
            CREATE TABLE IF NOT EXISTS frozen_batches (
                frozen_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                protocol_version INTEGER NOT NULL REFERENCES protocol_rules(version_id),
                reading_count INTEGER NOT NULL CHECK (reading_count > 0),
                choices TEXT NOT NULL
            );
        ''')

    @contextmanager
    def transaction(self, *, write: bool = True):
        self.connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield
            self.connection.commit()
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def begin_batch(self, batch_id: str, protocol_version: int) -> None:
        with self.transaction():
            self.bind_batch(batch_id, protocol_version)

    def bind_batch(self, batch_id: str, protocol_version: int) -> None:
        require_identifier(batch_id, 'batch_id')
        get_rule(self.connection, protocol_version)
        self.connection.execute('''
            INSERT INTO batches (batch_id, protocol_version) VALUES (?, ?)
            ON CONFLICT (batch_id) DO NOTHING
        ''', (batch_id, protocol_version))
        self.check_batch_rule(batch_id, protocol_version)

    def check_batch_rule(self, batch_id: str, protocol_version: int) -> None:
        row = self.connection.execute(
            'SELECT protocol_version FROM batches WHERE batch_id = ?', (batch_id,)
        ).fetchone()
        if row is None or row['protocol_version'] != protocol_version:
            raise ValueError('batch does not belong to the specified protocol version')

    def append_revision(self, batch_id: str, protocol_version: int, original_id: str,
                        level: str, value, weight: int, prior_revision_id: int | None) -> int:
        cursor = self.connection.execute('''
            INSERT INTO reading_revisions
            (batch_id, protocol_version, original_id, level, reading_value, weight_hex, prior_revision_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, protocol_version, original_id, level, encode_rational(value),
              format(weight, 'x'), prior_revision_id))
        revision_id = cursor.lastrowid
        self.connection.execute('''
            INSERT INTO reading_heads (batch_id, original_id, revision_id) VALUES (?, ?, ?)
            ON CONFLICT (batch_id, original_id) DO UPDATE SET revision_id = excluded.revision_id
        ''', (batch_id, original_id, revision_id))
        return revision_id

    def current_revision(self, batch_id: str, original_id: str) -> ReadingRevision | None:
        row = self.connection.execute('''
            SELECT r.* FROM reading_heads AS h
            JOIN reading_revisions AS r ON r.revision_id = h.revision_id
            WHERE h.batch_id = ? AND h.original_id = ?
        ''', (batch_id, original_id)).fetchone()
        return None if row is None else _decode_reading(row)

    def read_selected_revisions(self, batch_id: str, revision_ids=None) -> tuple[ReadingRevision, ...]:
        if revision_ids is None:
            rows = self.connection.execute('''
                SELECT r.* FROM reading_heads AS h
                JOIN reading_revisions AS r ON r.revision_id = h.revision_id
                WHERE h.batch_id = ? ORDER BY h.original_id
            ''', (batch_id,))
            return tuple(_decode_reading(row) for row in rows)
        if isinstance(revision_ids, (str, bytes)) or not isinstance(revision_ids, Sequence):
            raise ValueError('revision selection must be a sequence of revision ids')
        readings = []
        for revision_id in revision_ids:
            if not _is_id(revision_id):
                raise ValueError('invalid revision id in selection')
            row = self.connection.execute('''
                SELECT * FROM reading_revisions WHERE revision_id = ? AND batch_id = ?
            ''', (revision_id, batch_id)).fetchone()
            if row is None:
                raise ValueError(f'revision {revision_id} is unavailable in batch {batch_id!r}')
            readings.append(_decode_reading(row))
        return tuple(readings)

    def save_frozen_manifest(self, manifest: FrozenManifest) -> int:
        cursor = self.connection.execute('''
            INSERT INTO frozen_batches (batch_id, protocol_version, reading_count, choices)
            VALUES (?, ?, ?, ?)
        ''', (manifest.batch_id, manifest.protocol_version, len(manifest.choices),
              json.dumps(manifest.choices, ensure_ascii=False)))
        return cursor.lastrowid

    def read_frozen_manifest(self, frozen_id: int) -> FrozenManifest:
        if not _is_id(frozen_id):
            raise LookupError('unknown frozen batch')
        row = self.connection.execute(
            'SELECT * FROM frozen_batches WHERE frozen_id = ?', (frozen_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f'unknown frozen batch: {frozen_id}')
        entries = json.loads(row['choices'])
        if not isinstance(entries, list) or len(entries) != row['reading_count']:
            raise ValueError('incomplete frozen manifest')
        choices = []
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2 or not _is_id(entry[1]):
                raise ValueError('invalid frozen manifest entry')
            choices.append((require_identifier(entry[0], 'original_id'), entry[1]))
        return FrozenManifest(row['batch_id'], row['protocol_version'], tuple(choices))
