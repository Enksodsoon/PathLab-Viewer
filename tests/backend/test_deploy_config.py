from pathlib import Path


def test_tusd_uses_pathlab_data_owner() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    tusd_service = compose.split("\n  tusd:\n", maxsplit=1)[1].split(
        "\n  worker:\n", maxsplit=1
    )[0]

    assert 'user: "10001:10001"' in tusd_service
