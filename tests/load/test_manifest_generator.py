import json
from pathlib import Path

import pytest
from generate_manifest import ManifestError, generate_manifest, write_manifest


def make_public_slide(root: Path, public_id: str) -> Path:
    slide = root / public_id
    slide.mkdir(parents=True)
    (slide / "slide.dzi").write_text(
        '<Image TileSize="512" Overlap="1" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="4096" Height="4096"/></Image>',
        encoding="utf-8",
    )
    for level, side in ((10, 2), (11, 3), (12, 4), (13, 5)):
        directory = slide / "slide_files" / str(level)
        directory.mkdir(parents=True)
        for column in range(side):
            for row in range(side):
                (directory / f"{column}_{row}.jpeg").write_bytes(b"jpeg")
    return slide


def test_manifest_generation_is_deterministic_bounded_and_multilevel(
    tmp_path: Path,
) -> None:
    public_root = tmp_path / "public"
    make_public_slide(public_root, "public-1")

    first = generate_manifest(public_root, ["public-1"], seed=42)
    second = generate_manifest(public_root, ["public-1"], seed=42)

    assert first == second
    slide = first["slides"][0]
    assert set(slide) == {"publicId", "dziPath", "commonTiles", "randomTiles"}
    assert slide["publicId"] == "public-1"
    assert slide["dziPath"] == "slide.dzi"
    assert len(slide["commonTiles"]) <= 12
    assert len(slide["randomTiles"]) <= 256
    levels = {
        path.split("/")[1]
        for path in slide["commonTiles"] + slide["randomTiles"]
    }
    assert len(levels) == 3


def test_manifest_output_contains_no_private_metadata(tmp_path: Path) -> None:
    public_root = tmp_path / "private-host-path" / "public"
    make_public_slide(public_root, "public-1")
    output = tmp_path / "manifest.json"

    write_manifest(output, generate_manifest(public_root, ["public-1"], seed=1))

    serialized = output.read_text(encoding="utf-8")
    assert str(public_root) not in serialized
    assert "displayName" not in serialized
    assert "originalFilename" not in serialized
    assert json.loads(serialized)["slides"][0]["publicId"] == "public-1"


@pytest.mark.parametrize("public_id", ["../escape", "bad/id", "", "with space"])
def test_manifest_rejects_invalid_public_ids(tmp_path: Path, public_id: str) -> None:
    public_root = tmp_path / "public"
    public_root.mkdir()

    with pytest.raises(ManifestError):
        generate_manifest(public_root, [public_id], seed=1)


def test_manifest_rejects_symlinks(tmp_path: Path) -> None:
    public_root = tmp_path / "public"
    slide = make_public_slide(public_root, "public-1")
    outside = tmp_path / "outside.jpeg"
    outside.write_bytes(b"private")
    link = slide / "slide_files" / "13" / "linked.jpeg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")

    with pytest.raises(ManifestError, match="symlink"):
        generate_manifest(public_root, ["public-1"], seed=1)
