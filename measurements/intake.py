from dataclasses import dataclass

from measurements.repository import MeasurementRepository
from measurements.revisions import validate_correction
from protocol.levels import require_identifier
from protocol.rationals import parse_rational
from protocol.registry import get_rule


@dataclass(frozen=True)
class AcceptedReading:
    batch_id: str
    original_id: str
    revision_id: int


def submit_reading(repo: MeasurementRepository, batch_id: str, protocol_version: int,
                   original_id: str, level: str, value, weight: int, *,
                   corrects: int | None = None) -> AcceptedReading:
    require_identifier(batch_id, 'batch_id')
    require_identifier(original_id, 'original_id')
    require_identifier(level, 'level')
    exact_value = parse_rational(value)
    if type(weight) is not int or weight <= 0:
        raise ValueError('measurement weight must be a positive integer')
    with repo.transaction():
        rule = get_rule(repo.connection, protocol_version)
        rule.levels.rank(level)
        repo.bind_batch(batch_id, protocol_version)
        current = repo.current_revision(batch_id, original_id)
        validate_correction(current, corrects, batch_id, protocol_version, original_id)
        revision_id = repo.append_revision(batch_id, protocol_version, original_id, level,
                                           exact_value, weight, corrects)
    return AcceptedReading(batch_id, original_id, revision_id)
