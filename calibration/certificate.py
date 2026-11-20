from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from calibration.bounds import OptimalBounds
from calibration.fit import FitResult
from measurements.freeze import FrozenBatch
from protocol.levels import LevelOrder, require_identifier, validate_levels
from protocol.rationals import encode_rational, parse_rational
from protocol.units import validate_unit


@dataclass(frozen=True)
class CalibrationCertificate:
    frozen_id: int
    protocol_version: int
    protocol_id: str
    levels: LevelOrder
    unit: str
    domain: tuple[Fraction, Fraction]
    minimum_loss: Fraction
    bounds: OptimalBounds

    def contains_curve(self, values) -> bool:
        if (isinstance(values, (str, bytes)) or not isinstance(values, Sequence)
                or len(values) != len(self.levels.labels)):
            return False
        curve = tuple(parse_rational(value) for value in values)
        return (all(lo <= x <= hi for x, (lo, hi) in zip(curve, self.bounds.intervals))
                and all(left <= right for left, right in zip(curve, curve[1:])))

    def to_payload(self) -> dict:
        return {
            'version': 1,
            'frozen_id': self.frozen_id,
            'protocol_version': self.protocol_version,
            'protocol_id': self.protocol_id,
            'levels': list(self.levels.labels),
            'unit': self.unit,
            'domain': [encode_rational(value) for value in self.domain],
            'minimum_loss': encode_rational(self.minimum_loss),
            'bounds': [[encode_rational(lo), encode_rational(hi)] for lo, hi in self.bounds.intervals],
            'evidence': {'version': 1},
        }


def build_certificate(batch: FrozenBatch, fit: FitResult, bounds: OptimalBounds) -> CalibrationCertificate:
    rule = batch.rule
    certificate = CalibrationCertificate(
        batch.frozen_id, rule.version_id, rule.protocol_id, rule.levels, rule.unit,
        (rule.lower, rule.upper), fit.minimum_loss, bounds,
    )
    _validate(certificate)
    if not certificate.contains_curve(fit.representative):
        raise ValueError('certificate excludes the issued representative')
    return certificate


def _interval(raw) -> tuple[Fraction, Fraction]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError('expected a closed interval')
    return parse_rational(raw[0]), parse_rational(raw[1])


def _validate(certificate: CalibrationCertificate) -> None:
    if any(type(value) is not int or value <= 0
           for value in (certificate.frozen_id, certificate.protocol_version)):
        raise ValueError('invalid calibration source identity')
    lower, upper = certificate.domain
    intervals = certificate.bounds.intervals
    level_count = len(certificate.levels.labels)
    if lower > upper or certificate.minimum_loss < 0 or len(intervals) != level_count:
        raise ValueError('invalid calibration evidence dimensions or domain')
    if any(not lower <= lo <= hi <= upper for lo, hi in intervals):
        raise ValueError('projection outside calibration domain')
    for left, right in zip(intervals, intervals[1:]):
        if left[0] > right[0] or left[1] > right[1]:
            raise ValueError('projection is inconsistent with the ordered calibration')


def decode_certificate(payload: Mapping) -> CalibrationCertificate:
    if not isinstance(payload, Mapping) or type(payload.get('version')) is not int or payload['version'] != 1:
        raise ValueError('unsupported calibration certificate version')
    try:
        evidence = payload['evidence']
        if (not isinstance(evidence, Mapping) or type(evidence.get('version')) is not int
                or evidence['version'] != 1):
            raise ValueError('unsupported calibration evidence')
        certificate = CalibrationCertificate(
            payload['frozen_id'], payload['protocol_version'],
            require_identifier(payload['protocol_id'], 'protocol_id'), validate_levels(payload['levels']),
            validate_unit(payload['unit']), _interval(payload['domain']), parse_rational(payload['minimum_loss']),
            OptimalBounds(tuple(_interval(interval) for interval in payload['bounds'])),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError('incomplete calibration certificate') from exc
    _validate(certificate)
    return certificate
