class MaintenanceError(Exception):
    """Base error raised by the guarded maintenance subsystem."""


class PolicyDenied(MaintenanceError):
    """The requested maintenance operation is outside policy."""


class VerificationFailed(MaintenanceError):
    """A mutation could not be verified after execution."""
