"""Error hierarchy for SQLite graph store."""


class StoreError(Exception):
    """Base exception for store errors."""


class GraphNotFoundError(StoreError):
    """Raised when a graph id does not exist."""


class IncompatibleStoreError(StoreError):
    """Raised when store schema is incompatible with this code."""


class DuplicateGraphError(StoreError):
    """Raised when a graph creation collides with an existing id."""


class CorruptVectorError(StoreError):
    """Raised when embedding vector bytes are invalid."""


class MigrationFailedError(StoreError):
    """Raised when a migration cannot be applied."""

    def __init__(self, target_version: int, original: Exception):
        self.target_version = target_version
        self.original = original
        super().__init__(f"Migration to version {target_version} failed: {original}")
