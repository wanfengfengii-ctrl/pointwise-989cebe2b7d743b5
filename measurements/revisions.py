from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class ReadingRevision:
    revision_id: int
    batch_id: str
    protocol_version: int
    original_id: str
    level: str
    value: Fraction
    weight: int
    prior_revision_id: int | None


def validate_correction(current: ReadingRevision | None, target_id: int | None,
                        batch_id: str, protocol_version: int, original_id: str) -> None:
    if target_id is None:
        if current is not None:
            raise ValueError('existing measurement requires an explicit correction')
        return
    if (type(target_id) is not int or current is None or current.revision_id != target_id
            or (current.batch_id, current.protocol_version, current.original_id)
            != (batch_id, protocol_version, original_id)):
        raise ValueError('correction must target the current revision of this measurement')


def validate_revision_selection(readings: tuple[ReadingRevision, ...],
                                batch_id: str, protocol_version: int) -> None:
    if not readings:
        raise ValueError('cannot freeze an empty revision selection')
    originals = set()
    for reading in readings:
        if (reading.batch_id, reading.protocol_version) != (batch_id, protocol_version):
            raise ValueError('selected revision belongs to another batch or rule')
        if reading.original_id in originals:
            raise ValueError('choose at most one revision per original measurement')
        if reading.weight <= 0:
            raise ValueError('selected revision has an invalid weight')
        originals.add(reading.original_id)
