import json
import sqlite3
from fractions import Fraction
from itertools import combinations_with_replacement

from archive.retrieval import read_artifact
from calibration.certificate import decode_certificate
from calibration.issue import issue_calibration
from tests import LabCase, deny_commit


class CalibrationTests(LabCase):
    def test_known_ordered_fit_and_frozen_binding(self):
        frozen = self.seed('ordered', self.rule(), [('L', 0, 1), ('H', 2, 1)])
        issued = self.issue(frozen)
        self.assertEqual(issued.payload['minimum_loss'], '0')
        self.assertEqual(issued.payload['bounds'], [['0', '0'], ['2', '2']])
        self.assertEqual(issued.payload['frozen_id'], frozen.frozen_id)
        retrieved = read_artifact(self.archive, issued.artifact_id)
        self.assertEqual(retrieved.record, issued.record)
        self.assertEqual(retrieved.parent_chain, (('frozen_batch', frozen.frozen_id),))
        self.assertEqual(retrieved.receipt, issued.receipt)

    def test_weighted_repeats_all_contribute(self):
        frozen = self.seed('repeat', self.rule(), [('L', '2/3', 2), ('L', '2/3', 2), ('H', 0, 3)])
        self.assertEqual(len(frozen.manifest.choices), 3)
        issued = self.issue(frozen)
        # Choosing 2/3 for both coordinates costs 3 × 2/3. Below that
        # point the first level's total weight of 4 dominates the last's 3.
        self.assertEqual(issued.payload['minimum_loss'], '2')
        self.assertEqual(issued.payload['bounds'], [['2/3', '2/3'], ['2/3', '2/3']])

    def test_closed_singleton_with_out_of_domain_readings(self):
        frozen = self.seed('point', self.rule(lower='1/3', upper='1/3'), [('L', 0, 1), ('H', 2, 1)])
        issued = self.issue(frozen)
        self.assertEqual(issued.payload['minimum_loss'], '2')
        self.assertEqual(issued.payload['bounds'], [['1/3', '1/3'], ['1/3', '1/3']])
        certificate = decode_certificate(issued.payload)
        self.assertTrue(certificate.contains_curve(('1/3', '1/3')))
        self.assertFalse(certificate.contains_curve((0, 2)))

    def test_same_marginals_retain_joint_evidence(self):
        rule = self.rule()
        incident = self.seed('joined', rule, [('L', 2, 2), ('H', 0, 2)])
        control = self.seed('flexible', rule, [('L', 0, 1), ('L', 2, 1), ('H', 0, 1), ('H', 2, 1)])
        for frozen, allows_gap in ((incident, False), (control, True)):
            issued = self.issue(frozen)
            record = read_artifact(self.archive, issued.artifact_id).record
            certificate = decode_certificate(record.payload)
            self.assertEqual(record.payload['bounds'], [['0', '2'], ['0', '2']])
            self.assertEqual(certificate.minimum_loss, 4)
            self.assertEqual(certificate.frozen_id, frozen.frozen_id)
            self.assertEqual(certificate.protocol_version, rule.version_id)
            self.assertEqual(certificate.levels.labels, ('L', 'H'))
            self.assertEqual(certificate.unit, 'μm')
            self.assertTrue(certificate.contains_curve((0, 0)))
            self.assertEqual(certificate.contains_curve((1, 2)), allows_gap, 'V4_JOINT_EVIDENCE')
            self.assertNotIn('readings', record.payload)
            for reading in frozen.readings:
                self.assertNotIn(reading.original_id, record.body)

    def test_certificate_membership_against_direct_loss(self):
        levels = ('A', 'B', 'C', 'D')
        rows = [('A', '5/2', 2), ('B', '1/2', 2), ('D', '3/2', 1), ('D', 2, 1)]
        frozen = self.seed('direct', self.rule(levels=levels), rows)
        certificate = decode_certificate(self.issue(frozen).payload)
        values = [Fraction(index, 4) for index in range(9)]
        loss_by_curve = {}
        for curve in combinations_with_replacement(values, 4):
            points = dict(zip(levels, curve))
            loss_by_curve[curve] = sum(weight * abs(points[level] - Fraction(value)) for level, value, weight in rows)
        minimum = min(loss_by_curve.values())
        self.assertEqual(certificate.minimum_loss, minimum)
        optimal = [curve for curve, loss in loss_by_curve.items() if loss == minimum]
        self.assertEqual(certificate.bounds.intervals, tuple((min(col), max(col)) for col in zip(*optimal)))
        for curve, loss in loss_by_curve.items():
            self.assertEqual(certificate.contains_curve(curve), loss == minimum, curve)

    def test_certificate_rejects_tampered_loss_evidence(self):
        frozen = self.seed('joined', self.rule(), [('L', 2, 2), ('H', 0, 2)])
        payload = self.issue(frozen).payload
        certificate = decode_certificate(payload)
        self.assertFalse(certificate.contains_curve((1, 2)))
        self.assertFalse(certificate.contains_curve((3, 3)))
        forged = json.loads(json.dumps(payload))
        # Dropping the troublesome evidence must not silently widen the set.
        forged['evidence']['profiles'] = [[['0', 1]], [['0', 1]]]
        with self.assertRaisesRegex(ValueError, 'minimum loss'):
            decode_certificate(forged)
        forged = json.loads(json.dumps(payload))
        forged['minimum_loss'] = '0'
        forged['evidence']['profiles'] = []
        with self.assertRaises(ValueError):
            decode_certificate(forged)

    def test_invalid_frozen_source_publishes_nothing(self):
        frozen = self.seed('damaged', self.rule(), [('L', 0, 1), ('H', 2, 1)])
        with self.assertRaises(LookupError):
            issue_calibration(self.source, self.archive, frozen.frozen_id + 100)
        # Keep the stored manifest intact but make one of its exact references unresolvable.
        missing = frozen.readings[0].revision_id
        self.source.connection.execute('DELETE FROM reading_heads WHERE revision_id = ?', (missing,))
        self.source.connection.execute('DELETE FROM reading_revisions WHERE revision_id = ?', (missing,))
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.issue(frozen)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_issue_commit_failure_rolls_back(self):
        frozen = self.seed('ordered', self.rule(), [('L', 0, 1), ('H', 2, 1)])
        with deny_commit(self.archive) as attempts:
            with self.assertRaises(sqlite3.DatabaseError):
                self.issue(frozen)
        self.assertEqual(attempts, ['COMMIT'])
        self.stop_archive()
        self.open_archive()
        self.assertEqual(self.counts(), (0, 0, 0))
        self.assertEqual(read_artifact(self.archive, 1).status, 'not_found')
        successful = self.issue(frozen)
        self.assertEqual(read_artifact(self.archive, successful.artifact_id).receipt, successful.receipt)
