from dataclasses import dataclass

from archive.catalog import CALIBRATION, FROZEN_BATCH
from archive.retrieval import read_artifact
from calibration.certificate import CalibrationCertificate, decode_certificate
from protocol.thresholds import ThresholdPair, parse_thresholds


@dataclass(frozen=True)
class SwitchRequest:
    calibration_id: int
    certificate: CalibrationCertificate
    thresholds: ThresholdPair


def prepare_request(archive, calibration_id: int, low, high) -> SwitchRequest:
    thresholds = parse_thresholds(low, high)
    incoming = read_artifact(archive, calibration_id)
    if incoming.record is None or incoming.record.kind != CALIBRATION:
        raise ValueError('specified parent is not a published calibration')
    certificate = decode_certificate(incoming.record.payload)
    if incoming.parent_chain != ((FROZEN_BATCH, certificate.frozen_id),):
        raise ValueError('calibration body does not match the archived frozen source')
    return SwitchRequest(calibration_id, certificate, thresholds)
