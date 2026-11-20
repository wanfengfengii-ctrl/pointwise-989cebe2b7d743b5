from calibration.certificate import CalibrationCertificate
from protocol.thresholds import ThresholdPair
from switching.first_reach import (
    FirstReachConstraints, ReachPair, candidate_pairs, constraints_for_pair, pair_order_key,
)


def is_jointly_feasible(certificate: CalibrationCertificate, constraints: FirstReachConstraints) -> bool:
    intervals = certificate.bounds.intervals
    count = len(intervals)
    if len(constraints.lower) != count or len(constraints.strict_upper) != count:
        raise ValueError('constraint dimensions do not match the calibration order')

    smallest = certificate.domain[0]
    for (lo, hi), floor, cap in zip(intervals, constraints.lower, constraints.strict_upper):
        smallest = max(smallest, lo)
        if floor is not None:
            smallest = max(smallest, floor)
        if smallest > hi or (cap is not None and smallest >= cap):
            return False
    return True


def find_feasible_pairs(certificate: CalibrationCertificate, thresholds: ThresholdPair) -> tuple[ReachPair, ...]:
    order = certificate.levels
    feasible = []
    for pair in candidate_pairs(order):
        if is_jointly_feasible(certificate, constraints_for_pair(order, thresholds, pair)):
            feasible.append(pair)
    return tuple(sorted(feasible, key=lambda pair: pair_order_key(order, pair)))
