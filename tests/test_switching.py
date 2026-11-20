import json
from fractions import Fraction

from archive.retrieval import read_artifact
from calibration.certificate import decode_certificate
from measurements.freeze import freeze_revision
from switching.report import publish_switch_report
from tests import LabCase


class SwitchingTests(LabCase):
    def test_offline_accident_pair(self):
        frozen = self.seed('joined', self.rule(), [('L', 2, 2), ('H', 0, 2)])
        issued = self.issue(frozen)
        self.stop_source()
        report = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        expected = ((1, 1), (1, None), (None, None))
        self.assertEqual(report.pairs, expected, 'V5_OFFLINE_JOINT_REACH')
        self.assertEqual(report.parent_id, issued.artifact_id)
        stored = read_artifact(self.archive, report.artifact_id)
        self.assertEqual(stored.parent_chain, (('calibration', issued.artifact_id), ('frozen_batch', frozen.frozen_id)))
        self.assertEqual(stored.record.payload['pairs'], [list(pair) for pair in expected])
        self.assertEqual(stored.receipt, report.receipt)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v5',
            'input': {'readings': [2, 0], 'weights': [2, 2], 'domain': [0, 2], 'thresholds': [1, 2]},
            'expected': expected,
            'actual': report.pairs,
            'downstream_expected': {'pairs': expected, 'parent_id': issued.artifact_id},
            'downstream_actual': {'pairs': stored.record.payload['pairs'], 'parent_id': stored.record.parent_id},
            'code_paths': ['calibration/certificate.py', 'switching/feasibility.py', 'switching/report.py', 'archive/retrieval.py'],
            'oracle': 'The loss is 4 + 2 times the nonnegative gap, so the two fitted values coincide. Their common value lies below 1, in [1,2), or at 2.',
        }, sort_keys=True))

    def test_same_marginals_positive_control(self):
        rule = self.rule()
        accident = self.issue(self.seed('joined', rule, [('L', 2, 2), ('H', 0, 2)]))
        control = self.issue(self.seed('flexible', rule, [('L', 0, 1), ('L', 2, 1), ('H', 0, 1), ('H', 2, 1)]))
        self.assertEqual(accident.payload['minimum_loss'], control.payload['minimum_loss'])
        self.assertEqual(accident.payload['bounds'], control.payload['bounds'])
        self.stop_source()
        report = publish_switch_report(self.archive, control.artifact_id, 1, 2)
        self.assertEqual(report.pairs, ((1, 1), (1, 2), (1, None), (2, 2), (2, None), (None, None)))
        self.assertEqual(report.parent_id, control.artifact_id)

    def test_missing_middle(self):
        rule = self.rule(levels=('L', 'M', 'H'))
        issued = self.issue(self.seed('gap', rule, [('L', 0, 1), ('H', 2, 1)]))
        self.stop_source()
        report = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        self.assertEqual(report.pairs, ((2, 2), (2, 3), (3, 3)))

    def test_joint_curve_rejects_projection_only_pairs(self):
        # Marginally the middle level may sit anywhere in [0, 2], but every
        # optimal curve has the form (t, t, 2) with t < 2. Pairs such as
        # (2, 2) would need an optimal curve with the middle level at 2 while
        # the first stays below 1, which no single curve realises.
        rule = self.rule(levels=('A', 'B', 'C'))
        issued = self.issue(self.seed('ridge', rule, [('A', 2, 2), ('B', 0, 2), ('C', 2, 2)]))
        certificate = decode_certificate(issued.payload)
        self.assertEqual(certificate.bounds.intervals,
                         ((Fraction(0), Fraction(2)), (Fraction(0), Fraction(2)), (Fraction(2), Fraction(2))))
        self.assertTrue(certificate.contains_curve((0, 0, 2)))
        self.assertTrue(certificate.contains_curve((2, 2, 2)))
        self.assertFalse(certificate.contains_curve((0, 2, 2)))
        self.stop_source()
        report = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        self.assertEqual(report.pairs, ((1, 1), (1, 3), (3, 3)))

    def test_thresholds_outside_domain(self):
        issued = self.issue(self.seed('outside', self.rule(), [('L', 2, 2), ('H', 0, 2)]))
        self.stop_source()
        report = publish_switch_report(self.archive, issued.artifact_id, -1, 3)
        self.assertEqual(report.pairs, ((1, None),))

    def test_last_level_equality_is_a_reach(self):
        issued = self.issue(self.seed('equal', self.rule(), [('L', 2, 1), ('H', 2, 1)]))
        self.stop_source()
        report = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        self.assertEqual(report.pairs, ((1, 1),))

    def test_correction_selected_parent_and_reopened_history(self):
        rule = self.rule()
        low = self.reading('day', rule, 'A', 'L', 2)
        high = self.reading('day', rule, 'B', 'H', 2)
        old_frozen = freeze_revision(self.source, 'day', rule.version_id, [low.revision_id, high.revision_id])
        old_item = self.issue(old_frozen)
        self.stop_source()
        old_report = publish_switch_report(self.archive, old_item.artifact_id, 1, 2)
        before = read_artifact(self.archive, old_report.artifact_id)
        self.assertEqual(old_report.pairs, ((1, 1),))

        self.open_source()
        changed = self.reading('day', rule, 'A', 'L', 0, corrects=low.revision_id)
        new_frozen = freeze_revision(self.source, 'day', rule.version_id, [changed.revision_id, high.revision_id])
        new_item = self.issue(new_frozen)
        self.stop_source()
        new_report = publish_switch_report(self.archive, new_item.artifact_id, 1, 2)
        selected = publish_switch_report(self.archive, old_item.artifact_id, 1, 2)
        self.assertEqual(new_report.pairs, ((2, 2),))
        self.assertEqual(selected.pairs, ((1, 1),))
        self.assertEqual(selected.parent_id, old_item.artifact_id)
        self.assertEqual(read_artifact(self.archive, selected.artifact_id).record.parent_id, old_item.artifact_id)
        self.stop_archive()
        self.open_archive()
        self.assertEqual(self.counts(), (2, 3, 5))
        self.assertEqual(read_artifact(self.archive, old_report.artifact_id), before)
        for item, report, frozen, pair in ((old_item, old_report, old_frozen, [1, 1]),
                                          (new_item, new_report, new_frozen, [2, 2])):
            found = read_artifact(self.archive, report.artifact_id)
            self.assertEqual(found.record.payload['pairs'], [pair])
            self.assertEqual(found.parent_chain, (('calibration', item.artifact_id), ('frozen_batch', frozen.frozen_id)))
            self.assertEqual(found.receipt, report.receipt)
            parent = read_artifact(self.archive, item.artifact_id)
            self.assertEqual(parent.record, item.record)
            self.assertEqual(parent.receipt, item.receipt)

    def test_invalid_thresholds_publish_nothing(self):
        issued = self.issue(self.seed('ordered', self.rule(), [('L', 0, 1), ('H', 2, 1)]))
        before = self.counts()
        for low, high in ((1, 1), (2, 1), ('1/0', 2)):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                publish_switch_report(self.archive, issued.artifact_id, low, high)
        self.assertEqual(self.counts(), before)

    def test_invalid_parent_publishes_nothing(self):
        issued = self.issue(self.seed('ordered', self.rule(), [('L', 0, 1), ('H', 2, 1)]))
        report = publish_switch_report(self.archive, issued.artifact_id, 1, 2)
        before = self.counts()
        for parent in (report.artifact_id, report.artifact_id + 100):
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'published calibration'):
                publish_switch_report(self.archive, parent, 1, 2)
        self.assertEqual(self.counts(), before)
