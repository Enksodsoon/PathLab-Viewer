"""Public navigation retains declared calibration without exposing private metadata."""

import pytest
from test_alignment_api import _client, _correction_tiles, _headers
from test_alignment_engine_routes import _stack
from wsi_viewer.alignment_calibration import normalized_microns_per_pixel
from wsi_viewer.database import session_factory
from wsi_viewer.models import LibraryShare, ShareSlide, Slide


@pytest.mark.parametrize("delivery", ["individual", "shared-comparison"])
@pytest.mark.parametrize("units", ["common", "per-axis"])
def test_public_calibration_fields_survive_projection_but_private_fields_do_not(
    tmp_path, delivery, units
):
    _correction_tiles(tmp_path)
    calibration = {"width": 1000, "height": 800}
    if units == "common":
        calibration.update(physicalSizeX=250, physicalSizeY=500, physicalSizeUnit="nm")
    else:
        calibration.update(
            physicalSizeX=0.00025, physicalSizeY=500, physicalSizeXUnit="mm", physicalSizeYUnit="nm"
        )
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        with session_factory(client.app.state.settings)() as database:
            for name in ("slide-1", "slide-2"):
                database.get(Slide, name).slide_metadata = {
                    **calibration,
                    "futurePrivateField": "private-patient-identifier",
                    "bitsPerSample": 8,
                    "sourcePath": "C:/private-account/source.tif",
                }
            database.commit()
        if delivery == "individual":
            published = client.post(
                "/api/v1/admin/slides/slide-2/publish",
                headers=headers,
                json={"deidentifiedConfirmed": True},
            )
            assert published.status_code == 200, published.text
            response = client.get("/api/v1/public/slides/public-2")
            assert response.status_code == 200, response.text
            metadata = response.json()["metadata"]
        else:
            stack = _stack(client, headers)
            with session_factory(client.app.state.settings)() as database:
                share = LibraryShare(
                    public_id="calibration-share",
                    target_type="collection",
                    target_id="collection",
                    privacy_status="passed",
                )
                database.add(share)
                database.flush()
                database.add_all(
                    [
                        ShareSlide(share_id=share.id, slide_id=name, sort_order=index)
                        for index, name in enumerate(("slide-1", "slide-2"))
                    ]
                )
                database.commit()
            response = client.get(
                f"/api/v2/public/collections/calibration-share/comparisons/{stack['id']}"
            )
            assert response.status_code == 200, response.text
            metadata = response.json()["members"][1]["metadata"]
        assert metadata == calibration
        assert normalized_microns_per_pixel(metadata) == (0.25, 0.5)
        assert "private-patient-identifier" not in response.text
        assert "private-account" not in response.text
