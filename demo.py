import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.retrieval import read_artifact
from archive.storage import initialize_archive, open_archive
from calibration.issue import issue_calibration
from measurements.freeze import freeze_revision, load_frozen_batch
from measurements.intake import submit_reading
from measurements.repository import MeasurementRepository
from protocol.registry import register_protocol
from switching.report import publish_switch_report


def require_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f'expected {expected!r}, got {actual!r}')


def run_day(directory: Path):
    source_path = directory / 'measurements.sqlite'
    archive_path = directory / 'archive.sqlite'
    with closing(open_archive(archive_path)) as archive:
        initialize_archive(archive)
        with closing(MeasurementRepository.open(source_path)) as source:
            source.initialize()
            rule = register_protocol(source.connection, 'day-coating', ('coarse', 'fine'), 'μm', 0, 2)
            first = submit_reading(source, 'morning', rule.version_id, 'sheet-A', 'coarse', 2, 1)
            last = submit_reading(source, 'morning', rule.version_id, 'sheet-B', 'fine', 2, 1)
            old_frozen = freeze_revision(source, 'morning', rule.version_id, [first.revision_id, last.revision_id])
            old_item = issue_calibration(source, archive, old_frozen.frozen_id)
        old_report = publish_switch_report(archive, old_item.artifact_id, 1, 2)

        with closing(MeasurementRepository.open(source_path)) as source:
            source.initialize()
            correction = submit_reading(source, 'morning', rule.version_id, 'sheet-A', 'coarse', 0, 1,
                                        corrects=first.revision_id)
            new_frozen = freeze_revision(source, 'morning', rule.version_id, [correction.revision_id, last.revision_id])
            require_equal(load_frozen_batch(source, old_frozen.frozen_id), old_frozen)
            new_item = issue_calibration(source, archive, new_frozen.frozen_id)
        new_report = publish_switch_report(archive, new_item.artifact_id, 1, 2)

    expected = {'minimum_losses': ['0', '0'], 'bounds': [[['2', '2'], ['2', '2']], [['0', '0'], ['2', '2']]]}
    actual = {'minimum_losses': [old_item.payload['minimum_loss'], new_item.payload['minimum_loss']],
              'bounds': [old_item.payload['bounds'], new_item.payload['bounds']]}
    require_equal(actual, expected)
    require_equal(old_report.pairs, ((1, 1),))
    require_equal(new_report.pairs, ((2, 2),))
    downstream_expected = [
        {'pairs': [[1, 1]], 'parents': [['calibration', old_item.artifact_id], ['frozen_batch', old_frozen.frozen_id]],
         'receipt': old_report.receipt.receipt_id},
        {'pairs': [[2, 2]], 'parents': [['calibration', new_item.artifact_id], ['frozen_batch', new_frozen.frozen_id]],
         'receipt': new_report.receipt.receipt_id},
    ]
    downstream_actual = []
    with closing(open_archive(archive_path)) as archive:
        initialize_archive(archive)
        for report, item in ((old_report, old_item), (new_report, new_item)):
            found = read_artifact(archive, report.artifact_id)
            parent = read_artifact(archive, item.artifact_id)
            require_equal(found.status, 'found')
            require_equal(parent.record, item.record)
            require_equal(parent.receipt, item.receipt)
            require_equal(found.receipt.artifact_id, report.artifact_id)
            downstream_actual.append({'pairs': found.record.payload['pairs'],
                                      'parents': [list(step) for step in found.parent_chain],
                                      'receipt': found.receipt.receipt_id})
    require_equal(downstream_actual, downstream_expected)
    return {
        'case_id': 'v6',
        'input': {'unit': 'μm', 'original_readings': [2, 2], 'corrected_readings': [0, 2], 'thresholds': [1, 2]},
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': ['measurements/freeze.py', 'calibration/issue.py', 'switching/report.py', 'archive/retrieval.py'],
        'oracle': 'Both ordered input vectors fit their readings at zero loss. Read each first reach directly from its vector and compare the archive chain with the IDs returned at publication.',
    }


if __name__ == '__main__':
    with TemporaryDirectory(prefix='coating-lab-') as directory:
        result = run_day(Path(directory))
        print('POINTWISE_SCENARIO ' + json.dumps(result, ensure_ascii=False, sort_keys=True))
