from dataclasses import dataclass

from archive.catalog import SWITCH_REPORT
from archive.publication import publish_artifact
from archive.receipts import PublicationReceipt
from protocol.rationals import encode_rational
from protocol.thresholds import ThresholdPair
from switching.feasibility import find_feasible_pairs
from switching.first_reach import ReachPair
from switching.requests import prepare_request


@dataclass(frozen=True)
class SwitchReport:
    artifact_id: int
    parent_id: int
    thresholds: ThresholdPair
    pairs: tuple[ReachPair, ...]
    receipt: PublicationReceipt


def publish_switch_report(archive, calibration_id: int, low, high) -> SwitchReport:
    request = prepare_request(archive, calibration_id, low, high)
    certificate = request.certificate
    thresholds = request.thresholds
    pairs = find_feasible_pairs(certificate, thresholds)
    if not pairs:
        raise ValueError('calibration evidence admits no first-reach pair')
    payload = {
        'version': 1,
        'calibration_id': request.calibration_id,
        'protocol_version': certificate.protocol_version,
        'levels': list(certificate.levels.labels),
        'unit': certificate.unit,
        'thresholds': [encode_rational(thresholds.low), encode_rational(thresholds.high)],
        'pairs': [list(pair) for pair in pairs],
    }
    published = publish_artifact(archive, SWITCH_REPORT, payload, parent_id=request.calibration_id)
    return SwitchReport(published.artifact_id, request.calibration_id, thresholds, pairs, published.receipt)
