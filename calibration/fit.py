from dataclasses import dataclass, field
from fractions import Fraction
from itertools import accumulate

from calibration.loss import LossProfile
from protocol.rationals import parse_rational


@dataclass(frozen=True)
class _CostTables:
    grid: tuple[Fraction, ...]
    local: tuple[tuple[Fraction, ...], ...]
    prefix: tuple[tuple[Fraction, ...], ...]
    suffix: tuple[tuple[Fraction, ...], ...]


@dataclass(frozen=True)
class FitResult:
    minimum_loss: Fraction
    representative: tuple[Fraction, ...]
    _tables: _CostTables = field(repr=False, compare=False)


def _prefix_costs(rows: tuple[tuple[Fraction, ...], ...]) -> tuple[tuple[Fraction, ...], ...]:
    costs = [rows[0]]
    for row in rows[1:]:
        cheapest_predecessors = accumulate(costs[-1], min)
        costs.append(tuple(cost + previous for cost, previous in zip(row, cheapest_predecessors)))
    return tuple(costs)


def _cost_tables(profiles: tuple[LossProfile, ...], lower: Fraction, upper: Fraction) -> _CostTables:
    # Inside each cell cut out by the knots, the objective is affine. The
    # vertices of each cell with the order constraints use only grid values.
    nodes = {lower, upper}
    for profile in profiles:
        nodes.update(point for point in profile.breakpoints() if lower < point < upper)
    grid = tuple(sorted(nodes))
    local = tuple(profile.values_on(grid) for profile in profiles)
    prefix = _prefix_costs(local)
    reversed_local = tuple(row[::-1] for row in reversed(local))
    backward = _prefix_costs(reversed_local)
    suffix = tuple(row[::-1] for row in reversed(backward))
    return _CostTables(grid, local, prefix, suffix)


def _representative(tables: _CostTables, minimum: Fraction) -> tuple[Fraction, ...]:
    remaining = minimum
    first_allowed = 0
    curve = []
    for local, suffix in zip(tables.local, tables.suffix):
        chosen = next(index for index in range(first_allowed, len(tables.grid))
                      if suffix[index] == remaining)
        curve.append(tables.grid[chosen])
        remaining -= local[chosen]
        first_allowed = chosen
    return tuple(curve)


def minimize_loss(profiles: tuple[LossProfile, ...], lower, upper) -> FitResult:
    lower_value = parse_rational(lower)
    upper_value = parse_rational(upper)
    if not profiles or lower_value > upper_value:
        raise ValueError('fit requires an ordered profile sequence and a nonempty closed interval')
    tables = _cost_tables(profiles, lower_value, upper_value)
    minimum = min(tables.prefix[-1])
    return FitResult(minimum, _representative(tables, minimum), tables)
