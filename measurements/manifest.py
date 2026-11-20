from dataclasses import dataclass

from measurements.revisions import ReadingRevision, validate_revision_selection


@dataclass(frozen=True)
class FrozenManifest:
    batch_id: str
    protocol_version: int
    choices: tuple[tuple[str, int], ...]


def make_manifest(batch_id: str, protocol_version: int,
                  readings: tuple[ReadingRevision, ...]) -> FrozenManifest:
    validate_revision_selection(readings, batch_id, protocol_version)
    choices = tuple(sorted((reading.original_id, reading.revision_id) for reading in readings))
    return FrozenManifest(batch_id, protocol_version, choices)


def validate_manifest(manifest: FrozenManifest, readings: tuple[ReadingRevision, ...]) -> None:
    expected = make_manifest(manifest.batch_id, manifest.protocol_version, readings)
    if manifest != expected:
        raise ValueError('frozen manifest does not match the resolved source revisions')
