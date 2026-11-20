from collections.abc import Sequence
from dataclasses import dataclass


def require_identifier(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonempty string')
    return value


@dataclass(frozen=True)
class LevelOrder:
    labels: tuple[str, ...]

    def rank(self, level: str) -> int:
        """Return the zero-based position in the registered order."""
        try:
            return self.labels.index(level)
        except ValueError as exc:
            raise ValueError(f'unknown level: {level!r}') from exc


def validate_levels(levels) -> LevelOrder:
    if isinstance(levels, (str, bytes)) or not isinstance(levels, Sequence):
        raise ValueError('levels must be an ordered sequence of identifiers')
    if not 2 <= len(levels) <= 8:
        raise ValueError('a rule requires two to eight levels')
    labels = tuple(require_identifier(level, 'level') for level in levels)
    if len(set(labels)) != len(labels):
        raise ValueError('level identifiers must be unique')
    return LevelOrder(labels)
