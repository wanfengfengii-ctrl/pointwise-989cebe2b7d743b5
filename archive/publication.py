from dataclasses import dataclass

from archive.catalog import CALIBRATION, SWITCH_REPORT, ArtifactRecord, find_artifact, insert_artifact
from archive.receipts import PublicationReceipt, find_receipt, insert_receipt, make_receipt
from archive.storage import archive_transaction


@dataclass(frozen=True)
class PublishedArtifact:
    record: ArtifactRecord
    receipt: PublicationReceipt

    @property
    def artifact_id(self) -> int:
        return self.record.artifact_id

    @property
    def payload(self) -> dict:
        return self.record.payload


def _validate_reference(connection, kind: str, payload: dict, parent_id, frozen_id) -> None:
    if kind == CALIBRATION:
        if (parent_id is not None or type(frozen_id) is not int or not 1 <= frozen_id < 2**63
                or payload.get('frozen_id') != frozen_id):
            raise ValueError('calibration requires its fixed frozen source')
        return
    if kind == SWITCH_REPORT:
        parent = find_artifact(connection, parent_id)
        if (frozen_id is not None or payload.get('calibration_id') != parent_id or parent is None
                or parent.kind != CALIBRATION or find_receipt(connection, parent_id) is None):
            raise ValueError('report requires its exact published calibration parent')
        return
    raise ValueError('unknown publication kind')


def publish_artifact(connection, kind: str, payload: dict, *, parent_id: int | None = None,
                     frozen_id: int | None = None) -> PublishedArtifact:
    with archive_transaction(connection):
        _validate_reference(connection, kind, payload, parent_id, frozen_id)
        record = insert_artifact(connection, kind, payload, parent_id=parent_id, frozen_id=frozen_id)
        receipt = make_receipt(record.artifact_id)
        insert_receipt(connection, receipt)
    return PublishedArtifact(record, receipt)
