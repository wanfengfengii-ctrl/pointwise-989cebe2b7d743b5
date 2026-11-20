from dataclasses import dataclass

from measurements.manifest import FrozenManifest, make_manifest, validate_manifest
from measurements.repository import MeasurementRepository
from measurements.revisions import ReadingRevision
from protocol.levels import require_identifier
from protocol.registry import ProtocolRule, get_rule


@dataclass(frozen=True)
class FrozenBatch:
    frozen_id: int
    manifest: FrozenManifest
    rule: ProtocolRule
    readings: tuple[ReadingRevision, ...]


def _order_and_validate_levels(rule: ProtocolRule, readings: tuple[ReadingRevision, ...]):
    for reading in readings:
        rule.levels.rank(reading.level)
    return tuple(sorted(readings, key=lambda reading: reading.original_id))


def freeze_revision(repo: MeasurementRepository, batch_id: str, protocol_version: int,
                    revision_ids=None) -> FrozenBatch:
    require_identifier(batch_id, 'batch_id')
    with repo.transaction():
        rule = get_rule(repo.connection, protocol_version)
        repo.check_batch_rule(batch_id, protocol_version)
        readings = repo.read_selected_revisions(batch_id, revision_ids)
        manifest = make_manifest(batch_id, protocol_version, readings)
        ordered = _order_and_validate_levels(rule, readings)
        frozen_id = repo.save_frozen_manifest(manifest)
    return FrozenBatch(frozen_id, manifest, rule, ordered)


def load_frozen_batch(repo: MeasurementRepository, frozen_id: int) -> FrozenBatch:
    with repo.transaction(write=False):
        manifest = repo.read_frozen_manifest(frozen_id)
        rule = get_rule(repo.connection, manifest.protocol_version)
        repo.check_batch_rule(manifest.batch_id, manifest.protocol_version)
        revisions = tuple(revision_id for _, revision_id in manifest.choices)
        readings = repo.read_selected_revisions(manifest.batch_id, revisions)
        validate_manifest(manifest, readings)
        ordered = _order_and_validate_levels(rule, readings)
    return FrozenBatch(frozen_id, manifest, rule, ordered)
