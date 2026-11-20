from dataclasses import dataclass
from fractions import Fraction

from protocol.rationals import parse_rational


@dataclass(frozen=True)
class ThresholdPair:
    low: Fraction
    high: Fraction


def parse_thresholds(low, high) -> ThresholdPair:
    low_value = parse_rational(low)
    high_value = parse_rational(high)
    if low_value >= high_value:
        raise ValueError('thresholds must be strictly increasing')
    return ThresholdPair(low_value, high_value)
