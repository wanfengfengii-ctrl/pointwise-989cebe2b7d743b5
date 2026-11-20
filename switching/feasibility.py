from calibration.certificate import CalibrationCertificate
from calibration.fit import restricted_minimum_loss
from protocol.thresholds import ThresholdPair
from switching.first_reach import (
    FirstReachConstraints, ReachPair, candidate_pairs, constraints_for_pair, pair_order_key,
)


def is_jointly_feasible(certificate: CalibrationCertificate, constraints: FirstReachConstraints) -> bool:
    count = len(certificate.levels.labels)
    if len(constraints.lower) != count or len(constraints.strict_upper) != count:
        raise ValueError('constraint dimensions do not match the calibration order')
    # A pair counts only when one single optimal curve reaches both
    # thresholds at the claimed positions. Checking per-level projections
    # independently would admit combinations no optimal curve realises.
    loss = restricted_minimum_loss(certificate.profiles, *certificate.domain,
                                   constraints.lower, constraints.strict_upper)
    return loss is not None and loss == certificate.minimum_loss


def find_feasible_pairs(certificate: CalibrationCertificate, thresholds: ThresholdPair) -> tuple[ReachPair, ...]:
    order = certificate.levels
    feasible = []
    for pair in candidate_pairs(order):
        if is_jointly_feasible(certificate, constraints_for_pair(order, thresholds, pair)):
            feasible.append(pair)
    return tuple(sorted(feasible, key=lambda pair: pair_order_key(order, pair)))
