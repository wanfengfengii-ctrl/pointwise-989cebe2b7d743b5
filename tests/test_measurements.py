from fractions import Fraction

from measurements.freeze import freeze_revision, load_frozen_batch
from protocol.registry import get_rule, register_protocol
from tests import LabCase


class MeasurementTests(LabCase):
    def test_fraction_correction_and_reopen(self):
        rule = self.rule()
        first = self.reading('day', rule, 'A', 'L', '1/3')
        original = freeze_revision(self.source, 'day', rule.version_id, [first.revision_id])
        self.assertEqual(original.readings[0].value, Fraction(1, 3))
        changed = self.reading('day', rule, 'A', 'L', '2/3', corrects=first.revision_id)
        updated = freeze_revision(self.source, 'day', rule.version_id)
        explicit_history = freeze_revision(self.source, 'day', rule.version_id, [first.revision_id])
        self.assertNotEqual(original.frozen_id, updated.frozen_id)
        self.assertNotEqual(first.revision_id, changed.revision_id)
        self.assertEqual(updated.readings[0].prior_revision_id, first.revision_id)
        self.assertEqual(explicit_history.readings, original.readings)
        self.stop_source()
        self.open_source()
        self.source.initialize()
        self.assertEqual(get_rule(self.source.connection, rule.version_id), rule)
        before = load_frozen_batch(self.source, original.frozen_id)
        after = load_frozen_batch(self.source, updated.frozen_id)
        self.assertEqual((before.readings[0].value, after.readings[0].value), (Fraction(1, 3), Fraction(2, 3)))
        self.assertEqual(before.manifest.choices, (('A', first.revision_id),))
        self.assertEqual(after.manifest.choices, (('A', changed.revision_id),))
        self.assertEqual(self.source.current_revision('day', 'A'), after.readings[0])

    def test_reject_cross_original_and_stale_target(self):
        rule = self.rule()
        left = self.reading('day', rule, 'A', 'L', '1/3')
        right = self.reading('day', rule, 'B', 'H', 2)
        with self.assertRaisesRegex(ValueError, 'current revision'):
            self.reading('day', rule, 'A', 'L', '2/3', corrects=right.revision_id)
        original = freeze_revision(self.source, 'day', rule.version_id)
        self.assertEqual([(r.original_id, r.value, r.revision_id) for r in original.readings],
                         [('A', Fraction(1, 3), left.revision_id), ('B', Fraction(2), right.revision_id)])
        change = self.reading('day', rule, 'A', 'L', '2/3', corrects=left.revision_id)
        with self.assertRaisesRegex(ValueError, 'current revision'):
            self.reading('day', rule, 'A', 'L', 1, corrects=left.revision_id)
        self.assertEqual(self.source.current_revision('day', 'A').revision_id, change.revision_id)
        self.assertEqual(load_frozen_batch(self.source, original.frozen_id), original)

    def test_invalid_protocol_inputs(self):
        for levels, unit, lower, upper in [(('L', 'L'), 'μm', 0, 2), (('L', 'H'), 'μm', 3, 2),
                                            (('L', 'H'), 'kg', 0, 2)]:
            with self.subTest(levels=levels, unit=unit, lower=lower):
                with self.assertRaises(ValueError):
                    register_protocol(self.source.connection, 'bad', levels, unit, lower, upper)
        self.assertEqual(self.source.connection.execute('SELECT COUNT(*) FROM protocol_rules').fetchone()[0], 0)
        first = self.rule()
        second = self.rule(levels=('H', 'L'))
        self.assertNotEqual(first.version_id, second.version_id)
        self.assertEqual(get_rule(self.source.connection, first.version_id).levels.labels, ('L', 'H'))
        self.assertEqual(get_rule(self.source.connection, second.version_id).levels.labels, ('H', 'L'))

    def test_unknown_level_preserves_work_queue(self):
        rule = self.rule()
        accepted = self.reading('day', rule, 'A', 'L', 1)
        with self.assertRaisesRegex(ValueError, 'unknown level'):
            self.reading('day', rule, 'B', 'unknown', 2)
        self.assertIsNone(self.source.current_revision('day', 'B'))
        frozen = freeze_revision(self.source, 'day', rule.version_id)
        self.assertEqual(frozen.manifest.choices, (('A', accepted.revision_id),))

    def test_invalid_weight_preserves_work_queue(self):
        rule = self.rule()
        accepted = self.reading('day', rule, 'A', 'L', '1/3')
        for weight in (0, -3, True, Fraction(1, 2)):
            with self.subTest(weight=weight), self.assertRaisesRegex(ValueError, 'positive integer'):
                self.reading('day', rule, 'B', 'H', 2, weight)
        self.assertIsNone(self.source.current_revision('day', 'B'))
        frozen = freeze_revision(self.source, 'day', rule.version_id)
        self.assertEqual(frozen.manifest.choices, (('A', accepted.revision_id),))
        self.assertEqual(frozen.readings[0].value, Fraction(1, 3))

    def test_empty_batch_freezes_nothing(self):
        rule = self.rule()
        self.source.begin_batch('empty', rule.version_id)
        with self.assertRaisesRegex(ValueError, 'empty revision selection'):
            freeze_revision(self.source, 'empty', rule.version_id)
        self.assertEqual(self.frozen_count(), 0)

    def test_foreign_revision_and_duplicate_origin_freeze_nothing(self):
        rule = self.rule()
        old = self.reading('day', rule, 'A', 'L', 0)
        current = self.reading('day', rule, 'A', 'L', 1, corrects=old.revision_id)
        foreign = self.reading('other', rule, 'A', 'L', 2)
        with self.assertRaises(ValueError):
            freeze_revision(self.source, 'day', rule.version_id, [foreign.revision_id])
        with self.assertRaises(ValueError):
            freeze_revision(self.source, 'day', rule.version_id, [old.revision_id, current.revision_id])
        self.assertEqual(self.frozen_count(), 0)
        frozen = freeze_revision(self.source, 'day', rule.version_id, [current.revision_id])
        self.assertEqual(frozen.manifest.choices, (('A', current.revision_id),))
