class CustomError(Exception):
    pass


class UploadRejectedError(CustomError):
    pass


class SyncCycleError(CustomError):
    """Raised when sync token doesn't change between iterations, indicating an infinite sync loop."""

    pass
