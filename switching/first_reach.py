from dataclasses import dataclass
from fractions import Fraction

from protocol.levels import LevelOrder
from protocol.thresholds import ThresholdPair

NOT_REACHED = None
ReachPair = tuple[int | None, int | None]


@dataclass(frozen=True)
class FirstReachConstraints:
    lower: tuple[Fraction | None, ...]
    strict_upper: tuple[Fraction | None, ...]


def _position(level_count: int, reach: int | None) -> int:
    if reach is NOT_REACHED:
        return level_count + 1
    if type(reach) is not int or not 1 <= reach <= level_count:
        raise ValueError('first-reach level outside the registered order')
    return reach


def pair_order_key(order: LevelOrder, pair: ReachPair) -> tuple[int, int]:
    low, high = pair
    return _position(len(order.labels), low), _position(len(order.labels), high)


def candidate_pairs(order: LevelOrder) -> tuple[ReachPair, ...]:
    positions = (*range(1, len(order.labels) + 1), NOT_REACHED)
    return tuple((low, high) for index, low in enumerate(positions) for high in positions[index:])


def constraints_for_pair(order: LevelOrder, thresholds: ThresholdPair, pair: ReachPair) -> FirstReachConstraints:
    low_reach, high_reach = pair_order_key(order, pair)
    if low_reach > high_reach:
        raise ValueError('the low threshold cannot first be reached after the high threshold')
    lower = []
    strict_upper = []
    for position in range(1, len(order.labels) + 1):
        if position < low_reach:
            floor, ceiling = None, thresholds.low
        elif position < high_reach:
            floor, ceiling = thresholds.low, thresholds.high
        else:
            floor, ceiling = thresholds.high, None
        lower.append(floor)
        strict_upper.append(ceiling)
    return FirstReachConstraints(tuple(lower), tuple(strict_upper))
