import sqlite3

from archive.receipts import find_receipt
from archive.retrieval import read_artifact
from switching.report import publish_switch_report
from tests import LabCase, deny_commit


class PublicationTests(LabCase):
    def test_report_commit_failure_rolls_back(self):
        frozen = self.seed('ordered', self.rule(), [('L', 0, 1), ('H', 2, 1)])
        issued = self.issue(frozen)
        self.stop_source()
        original = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        original_record = read_artifact(self.archive, original.artifact_id)
        before = self.counts()
        self.assertEqual(before, (1, 1, 2))
        candidate = original.artifact_id + 1
        with deny_commit(self.archive) as attempts:
            with self.assertRaises(sqlite3.DatabaseError):
                publish_switch_report(self.archive, issued.artifact_id, '1/3', 2)
        self.assertEqual(attempts, ['COMMIT'])
        self.stop_archive()
        self.open_archive()
        self.assertEqual(self.counts(), before)
        missing = read_artifact(self.archive, candidate)
        self.assertEqual(missing.status, 'not_found')
        self.assertIsNone(missing.record)
        self.assertIsNone(missing.receipt)
        self.assertEqual(missing.parent_chain, ())
        self.assertIsNone(find_receipt(self.archive, candidate))
        self.assertEqual(read_artifact(self.archive, original.artifact_id), original_record)
        self.assertEqual(original_record.receipt, original.receipt)
