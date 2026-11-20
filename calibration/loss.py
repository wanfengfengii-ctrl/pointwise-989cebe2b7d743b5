from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from measurements.revisions import ReadingRevision
from protocol.levels import LevelOrder


@dataclass(frozen=True)
class LossProfile:
    knots: tuple[tuple[Fraction, int], ...]

    def value_at(self, value: Fraction) -> Fraction:
        return sum((weight * abs(value - knot) for knot, weight in self.knots), Fraction(0))

    def breakpoints(self) -> tuple[Fraction, ...]:
        return tuple(knot for knot, _ in self.knots)

    def values_on(self, grid: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
        """Evaluate on a sorted nonempty grid by sweeping the changes in slope."""
        position = grid[0]
        loss = self.value_at(position)
        slope = -sum(weight for _, weight in self.knots)
        pending = iter(self.knots)
        knot = next(pending, None)
        values = []
        for target in grid:
            while knot is not None and knot[0] <= target:
                point, weight = knot
                if point > position:
                    loss += slope * (point - position)
                    position = point
                slope += 2 * weight
                knot = next(pending, None)
            loss += slope * (target - position)
            position = target
            values.append(loss)
        return tuple(values)


def build_loss_profiles(order: LevelOrder, readings: tuple[ReadingRevision, ...]) -> tuple[LossProfile, ...]:
    by_level = [Counter() for _ in order.labels]
    for reading in readings:
        index = order.rank(reading.level)
        by_level[index][reading.value] += reading.weight
    return tuple(LossProfile(tuple(sorted(weights.items()))) for weights in by_level)
