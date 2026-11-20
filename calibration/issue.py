from archive.catalog import CALIBRATION
from archive.publication import PublishedArtifact, publish_artifact
from calibration.bounds import project_optimal_bounds
from calibration.certificate import build_certificate
from calibration.fit import minimize_loss
from calibration.loss import build_loss_profiles
from measurements.freeze import load_frozen_batch
from measurements.repository import MeasurementRepository


def issue_calibration(repo: MeasurementRepository, archive, frozen_id: int) -> PublishedArtifact:
    batch = load_frozen_batch(repo, frozen_id)
    profiles = build_loss_profiles(batch.rule.levels, batch.readings)
    fit = minimize_loss(profiles, batch.rule.lower, batch.rule.upper)
    bounds = project_optimal_bounds(fit)
    certificate = build_certificate(batch, fit, bounds, profiles)
    return publish_artifact(archive, CALIBRATION, certificate.to_payload(), frozen_id=batch.frozen_id)
