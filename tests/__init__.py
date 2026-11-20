"""Business regressions against isolated source and archive databases."""

import sqlite3
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.storage import initialize_archive, open_archive
from calibration.issue import issue_calibration
from measurements.freeze import freeze_revision
from measurements.intake import submit_reading
from measurements.repository import MeasurementRepository
from protocol.registry import register_protocol


class LabCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = None
        self.archive = None
        self.addCleanup(self._close_handles)
        self.source_path = Path(directory.name) / 'source.sqlite'
        self.archive_path = Path(directory.name) / 'archive.sqlite'
        self.open_source()
        self.open_archive()

    def _close_handles(self):
        self.stop_source()
        self.stop_archive()

    def open_source(self):
        self.source = MeasurementRepository.open(self.source_path)
        self.source.initialize()

    def stop_source(self):
        if self.source is not None:
            self.source.close()
            self.source = None

    def open_archive(self):
        self.archive = open_archive(self.archive_path)
        initialize_archive(self.archive)

    def stop_archive(self):
        if self.archive is not None:
            self.archive.close()
            self.archive = None

    def rule(self, levels=('L', 'H'), lower=0, upper=2):
        return register_protocol(self.source.connection, 'coat-thickness', levels, 'μm', lower, upper)

    def reading(self, batch, rule, original, level, value, weight=1, *, corrects=None):
        return submit_reading(self.source, batch, rule.version_id, original, level, value,
                              weight, corrects=corrects)

    def seed(self, batch, rule, readings):
        accepted = [self.reading(batch, rule, f'{batch}-observation-{index}', level, value, weight)
                    for index, (level, value, weight) in enumerate(readings, 1)]
        return freeze_revision(self.source, batch, rule.version_id,
                               [item.revision_id for item in accepted])

    def issue(self, frozen):
        return issue_calibration(self.source, self.archive, frozen.frozen_id)

    def counts(self):
        calibrations, reports = self.archive.execute('''
            SELECT COUNT(CASE WHEN kind = 'calibration' THEN 1 END),
                   COUNT(CASE WHEN kind = 'switch_report' THEN 1 END) FROM artifacts
        ''').fetchone()
        receipts = self.archive.execute('SELECT COUNT(*) FROM publication_receipts').fetchone()[0]
        return calibrations, reports, receipts

    def frozen_count(self):
        return self.source.connection.execute('SELECT COUNT(*) FROM frozen_batches').fetchone()[0]


@contextmanager
def deny_commit(connection):
    attempts = []

    def authorize(action, operation, *_):
        if action == sqlite3.SQLITE_TRANSACTION and operation == 'COMMIT':
            attempts.append(operation)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    try:
        yield attempts
    finally:
        connection.set_authorizer(None)
