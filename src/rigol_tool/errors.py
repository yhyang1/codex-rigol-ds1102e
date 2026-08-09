class RigolError(Exception):
    """Base error with a stable process exit code."""

    exit_code = 3


class ConfigurationError(RigolError):
    exit_code = 2


class DeviceIdentityError(RigolError):
    exit_code = 2


class AcquisitionError(RigolError):
    exit_code = 3


class WaveformDataError(AcquisitionError):
    """Malformed, incomplete, or inconsistent waveform transfer."""


class TriggerTimeoutError(AcquisitionError):
    pass


class ArtifactError(RigolError):
    exit_code = 4


class RestorationError(RigolError):
    exit_code = 5
