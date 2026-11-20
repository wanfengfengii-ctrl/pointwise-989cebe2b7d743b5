from dataclasses import dataclass
from fractions import Fraction

from calibration.fit import FitResult


@dataclass(frozen=True)
class OptimalBounds:
    intervals: tuple[tuple[Fraction, Fraction], ...]


def project_optimal_bounds(fit: FitResult) -> OptimalBounds:
    tables = fit._tables
    intervals = []
    for prefix, suffix, local in zip(tables.prefix, tables.suffix, tables.local):
        # Both costs include this coordinate, so subtract its local loss once.
        admitted = [value for value, left, right, own in zip(tables.grid, prefix, suffix, local)
                    if left + right - own == fit.minimum_loss]
        intervals.append((admitted[0], admitted[-1]))
    return OptimalBounds(tuple(intervals))
