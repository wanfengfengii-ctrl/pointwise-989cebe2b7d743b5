from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from calibration.bounds import OptimalBounds, project_optimal_bounds
from calibration.fit import FitResult, minimize_loss
from calibration.loss import LossProfile
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
    profiles: tuple[LossProfile, ...]

    def contains_curve(self, values) -> bool:
        if (isinstance(values, (str, bytes)) or not isinstance(values, Sequence)
                or len(values) != len(self.levels.labels)):
            return False
        curve = tuple(parse_rational(value) for value in values)
        lower, upper = self.domain
        if not all(lower <= value <= upper for value in curve):
            return False
        if not all(left <= right for left, right in zip(curve, curve[1:])):
            return False
        # The aggregate loss profile is the complete mathematical evidence:
        # a monotone in-domain curve is optimal exactly when its own loss
        # reaches the stated minimum. Marginal projections are not enough,
        # because they admit combinations that no single curve can realise.
        loss = sum((profile.value_at(value) for profile, value in zip(self.profiles, curve)), Fraction(0))
        return loss == self.minimum_loss

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
            'evidence': {
                'version': 1,
                'profiles': [
                    [[encode_rational(knot), weight] for knot, weight in profile.knots]
                    for profile in self.profiles
                ],
            },
        }


def build_certificate(batch: FrozenBatch, fit: FitResult, bounds: OptimalBounds,
                      profiles: tuple[LossProfile, ...]) -> CalibrationCertificate:
    rule = batch.rule
    certificate = CalibrationCertificate(
        batch.frozen_id, rule.version_id, rule.protocol_id, rule.levels, rule.unit,
        (rule.lower, rule.upper), fit.minimum_loss, bounds, profiles,
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
    if len(certificate.profiles) != level_count:
        raise ValueError('loss evidence dimensions do not match the calibration order')
    for profile in certificate.profiles:
        knots = profile.knots
        if any(type(weight) is not int or weight <= 0 for _, weight in knots):
            raise ValueError('loss evidence requires positive integer weights')
        if any(left >= right for (left, _), (right, _) in zip(knots, knots[1:])):
            raise ValueError('loss evidence knots must be strictly ordered')
    if any(not lower <= lo <= hi <= upper for lo, hi in intervals):
        raise ValueError('projection outside calibration domain')
    for left, right in zip(intervals, intervals[1:]):
        if left[0] > right[0] or left[1] > right[1]:
            raise ValueError('projection is inconsistent with the ordered calibration')


def _profiles_from_evidence(evidence: Mapping, level_count: int) -> tuple[LossProfile, ...]:
    raw_profiles = evidence.get('profiles')
    if not isinstance(raw_profiles, (list, tuple)) or len(raw_profiles) != level_count:
        raise ValueError('incomplete calibration evidence')
    profiles = []
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, (list, tuple)):
            raise ValueError('invalid calibration evidence profile')
        knots = []
        for entry in raw_profile:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError('invalid calibration evidence knot')
            knot = parse_rational(entry[0])
            weight = entry[1]
            if type(weight) is not int or weight <= 0:
                raise ValueError('loss evidence requires positive integer weights')
            knots.append((knot, weight))
        profiles.append(LossProfile(tuple(knots)))
    return tuple(profiles)


def decode_certificate(payload: Mapping) -> CalibrationCertificate:
    if not isinstance(payload, Mapping) or type(payload.get('version')) is not int or payload['version'] != 1:
        raise ValueError('unsupported calibration certificate version')
    try:
        evidence = payload['evidence']
        if (not isinstance(evidence, Mapping) or type(evidence.get('version')) is not int
                or evidence['version'] != 1):
            raise ValueError('unsupported calibration evidence')
        levels = validate_levels(payload['levels'])
        certificate = CalibrationCertificate(
            payload['frozen_id'], payload['protocol_version'],
            require_identifier(payload['protocol_id'], 'protocol_id'), levels,
            validate_unit(payload['unit']), _interval(payload['domain']), parse_rational(payload['minimum_loss']),
            OptimalBounds(tuple(_interval(interval) for interval in payload['bounds'])),
            _profiles_from_evidence(evidence, len(levels.labels)),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError('incomplete calibration certificate') from exc
    _validate(certificate)
    # Re-derive the optimum from the stored loss evidence so that the
    # certificate admits exactly the optimal curves it claims to admit.
    fitted = minimize_loss(certificate.profiles, *certificate.domain)
    if fitted.minimum_loss != certificate.minimum_loss:
        raise ValueError('calibration evidence does not realise the stated minimum loss')
    if project_optimal_bounds(fitted).intervals != certificate.bounds.intervals:
        raise ValueError('calibration projections do not match the stored loss evidence')
    return certificate
