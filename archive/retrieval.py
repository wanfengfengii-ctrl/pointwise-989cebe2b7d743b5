from dataclasses import dataclass
from typing import Literal

from archive.catalog import CALIBRATION, FROZEN_BATCH, SWITCH_REPORT, ArtifactRecord, find_artifact
from archive.receipts import PublicationReceipt, find_receipt


@dataclass(frozen=True)
class ArtifactReadResult:
    status: Literal['found', 'not_found']
    record: ArtifactRecord | None = None
    parent_chain: tuple[tuple[str, int], ...] = ()
    receipt: PublicationReceipt | None = None


def _parent_chain(connection, record: ArtifactRecord) -> tuple[tuple[str, int], ...]:
    if record.kind == CALIBRATION and record.frozen_id is not None:
        return ((FROZEN_BATCH, record.frozen_id),)
    if record.kind == SWITCH_REPORT:
        parent = find_artifact(connection, record.parent_id)
        if parent is not None and parent.kind == CALIBRATION and parent.frozen_id is not None:
            return ((CALIBRATION, parent.artifact_id), (FROZEN_BATCH, parent.frozen_id))
    raise ValueError('incomplete archived parent chain')


def read_artifact(connection, artifact_id: int) -> ArtifactReadResult:
    record = find_artifact(connection, artifact_id)
    if record is None:
        return ArtifactReadResult('not_found')
    receipt = find_receipt(connection, record.artifact_id)
    if receipt is None:
        raise ValueError('archived publication has no receipt')
    return ArtifactReadResult('found', record, _parent_chain(connection, record), receipt)
