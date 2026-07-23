from .config import Settings, validate_runtime_security


def main() -> None:
    validate_runtime_security(Settings())
