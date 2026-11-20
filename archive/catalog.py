import json
import sqlite3
from dataclasses import dataclass

CALIBRATION = 'calibration'
SWITCH_REPORT = 'switch_report'
FROZEN_BATCH = 'frozen_batch'


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: int
    kind: str
    body: str
    parent_id: int | None
    frozen_id: int | None

    @property
    def payload(self) -> dict:
        return json.loads(self.body)


def insert_artifact(connection: sqlite3.Connection, kind: str, payload: dict, *,
                    parent_id: int | None, frozen_id: int | None) -> ArtifactRecord:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    cursor = connection.execute('''
        INSERT INTO artifacts (kind, body, parent_id, frozen_id) VALUES (?, ?, ?, ?)
    ''', (kind, body, parent_id, frozen_id))
    return ArtifactRecord(cursor.lastrowid, kind, body, parent_id, frozen_id)


def find_artifact(connection: sqlite3.Connection, artifact_id: int) -> ArtifactRecord | None:
    if type(artifact_id) is not int or not 1 <= artifact_id < 2**63:
        return None
    row = connection.execute('''
        SELECT artifact_id, kind, body, parent_id, frozen_id FROM artifacts WHERE artifact_id = ?
    ''', (artifact_id,)).fetchone()
    return None if row is None else ArtifactRecord(*row)
