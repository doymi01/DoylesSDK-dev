class CorruptStoreError(Exception):
    """Raised when the fallback credential store cannot be decrypted or parsed."""

    pass


__all__ = ["CorruptStoreError"]
