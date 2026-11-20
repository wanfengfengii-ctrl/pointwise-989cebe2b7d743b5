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


def restricted_minimum_loss(profiles: tuple[LossProfile, ...], lower, upper,
                            floors, caps) -> Fraction | None:
    """Cheapest monotone in-domain curve obeying inclusive floors and strict caps.

    Returns ``None`` when no curve satisfies the per-level constraints. The
    grid is enriched with every floor and cap so that an affine cell is never
    cut inside; a strict cap therefore admits only grid values strictly below
    it, which is exactly the open boundary the caller asked for.
    """
    lower_value = parse_rational(lower)
    upper_value = parse_rational(upper)
    if (not profiles or lower_value > upper_value
            or len(floors) != len(profiles) or len(caps) != len(profiles)):
        raise ValueError('restricted fit requires ordered profiles and matching constraints')
    nodes = {lower_value, upper_value}
    for profile in profiles:
        nodes.update(point for point in profile.breakpoints() if lower_value < point < upper_value)
    for bound in (*floors, *caps):
        if bound is not None and lower_value < bound < upper_value:
            nodes.add(bound)
    grid = tuple(sorted(nodes))
    allowed = []
    for floor, cap in zip(floors, caps):
        allowed.append(tuple(
            (floor is None or value >= floor) and (cap is None or value < cap)
            for value in grid
        ))
    costs = None
    for profile, mask in zip(profiles, allowed):
        local = profile.values_on(grid)
        if costs is None:
            costs = [cost if permit else None for cost, permit in zip(local, mask)]
            continue
        updated = []
        best = None
        for cost, permit, previous in zip(local, mask, costs):
            # ``previous`` is the cheapest prefix ending at or before this
            # grid point, so the nondecreasing order is enforced here.
            best = _cheaper(best, previous)
            updated.append(None if not permit or best is None else best + cost)
        costs = updated
    feasible = [cost for cost in costs if cost is not None]
    return min(feasible) if feasible else None


def _cheaper(left: Fraction | None, right: Fraction | None) -> Fraction | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)
