import os

from .config import Settings, validate_runtime_security


def main() -> None:
    if "PATHLAB_SECRET_KEY" not in os.environ:
        raise RuntimeError("PATHLAB_SECRET_KEY must be set explicitly for deployment")
    validate_runtime_security(Settings())
