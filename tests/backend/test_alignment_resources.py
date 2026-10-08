import hashlib
from types import SimpleNamespace

import pytest
from wsi_viewer import alignment_engines as engines
from wsi_viewer.alignment import AlignmentRejected


def assets(tmp_path):
    settings = {}
    for asset in ("Disk", "LightGlue"):
        path = tmp_path / (asset + ".pth")
        path.write_bytes(asset.encode())
        settings[f"valis{asset}WeightsPath"] = str(path)
        settings[f"valis{asset}WeightsSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return settings


def test_valis_missing_or_changed_explicit_assets_are_unavailable(tmp_path):
    assert engines.engine_resource_availability("valis", {})[0] is False
    configured = assets(tmp_path)
    assert engines.engine_resource_availability("native-valis", configured)[0] is True
    (tmp_path / "Disk.pth").write_bytes(b"changed")
    assert engines.engine_resource_availability("valis-rigid-wsireg", configured)[0] is False


def test_valis_missing_assets_fail_before_model_import(tmp_path, monkeypatch):
    import importlib

    from PIL import Image

    monkeypatch.setattr(engines.ValisEngine, "available", lambda _: (True, None))
    monkeypatch.setattr(
        importlib, "import_module", lambda name: pytest.fail("model imported without resources")
    )
    image = Image.new("RGB", (10, 10))
    with pytest.raises(AlignmentRejected, match="verified.*VALIS"):
        engines.ValisEngine().register(
            engines.EngineInput(image, image, image.size, image.size, tmp_path), lambda _: None
        )


def test_valis_loader_uses_only_verified_local_files_and_restores_hub(tmp_path, monkeypatch):
    import sys

    from wsi_viewer.alignment_resources import admitted_valis_resources

    configured = assets(tmp_path)
    loads = []

    def original(*args, **kwargs):
        pytest.fail("implicit network download")

    torch = SimpleNamespace(
        hub=SimpleNamespace(load_state_dict_from_url=original),
        load=lambda path, **kw: loads.append((str(path), kw)) or {"local": str(path)},
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    with admitted_valis_resources(configured):
        value = torch.hub.load_state_dict_from_url(
            "https://raw.githubusercontent.com/cvlab-epfl/disk/master/depth-save.pth",
            map_location="cpu",
        )
        assert value["local"] == configured["valisDiskWeightsPath"]
        assert loads[0][1]["weights_only"] is True
        with pytest.raises(AlignmentRejected, match="unadmitted"):
            torch.hub.load_state_dict_from_url("https://example.test/other.pth")
    assert torch.hub.load_state_dict_from_url is original
