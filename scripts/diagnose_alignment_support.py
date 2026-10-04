"""Diagnose frozen support using saved transforms; never fit or change registration gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from wsi_viewer.alignment import (
    AlignmentRejected,
    _registration_triangles,
    _structure,
    map_registration_point,
)
from wsi_viewer.alignment_benchmark import _input_digest


def holes(mask):
    _, labels = cv2.connectedComponents((mask == 0).astype(np.uint8))
    external = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    return (mask == 0) & ~np.isin(labels, external)


def point_kind(mask, point):
    x, y = np.rint(point).astype(int)
    if not 0 <= x < mask.shape[1] or not 0 <= y < mask.shape[0]:
        return "outside-frame"
    if mask[y, x]:
        return "tissue"
    return "enclosed-background-mask-hole" if holes(mask)[y, x] else "external-background"


def variants(side):
    with Image.open(Path(side["path"]) / "thumbnail.jpg") as opened:
        image = opened.convert("RGB")
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    rgb = np.asarray(image)
    result = {}
    for name, thin in (("normal", False), ("thin", True)):
        try:
            result[name] = _structure(
                rgb, preserve_thin_tissue=thin, cropped=side.get("tissueCrop", False)
            )[1]
        except AlignmentRejected:
            result[name] = None
    background = np.percentile(rgb[::8, ::8].reshape(-1, 3), 70, axis=0)
    corrected = np.clip(rgb.astype(np.float32) * (255 / np.maximum(background, 1)), 0, 255).astype(
        np.uint8
    )
    for name, thin in (("calibrated-normal", False), ("calibrated-thin", True)):
        try:
            result[name] = _structure(
                corrected, preserve_thin_tissue=thin, cropped=side.get("tissueCrop", False)
            )[1]
        except AlignmentRejected:
            result[name] = None
    result["prepared-primary"] = next(
        (
            result[name]
            for name in ("normal", "thin", "calibrated-thin")
            if result[name] is not None
        ),
        None,
    )
    result["prepared-thin"] = (
        result["thin"] if result["normal"] is not None else result["prepared-primary"]
    )
    primary = result["prepared-primary"]
    result["prepared-calibrated"] = (
        result["calibrated-thin"]
        if (
            primary is not None
            and (result["normal"] is not None or result["thin"] is not None)
            and np.count_nonzero(primary) >= primary.size * 0.15
        )
        else None
    )
    return result


def fixed_transform_dice(reference, moving, affine, reference_size, moving_size):
    if reference is None or moving is None:
        return None
    ref = np.diag(
        [reference.shape[1] / reference_size[0], reference.shape[0] / reference_size[1], 1]
    )
    mov = np.diag([moving_size[0] / moving.shape[1], moving_size[1] / moving.shape[0], 1])
    matrix = ref @ np.vstack((affine, [0, 0, 1])) @ mov
    warped = cv2.warpAffine(moving, matrix[:2], reference.shape[::-1])
    return (
        2
        * np.count_nonzero((warped > 0) & (reference > 0))
        / max(1, np.count_nonzero(warped) + np.count_nonzero(reference))
    )


def fixed_grid_meshes(reference, moving, affine, reference_size, moving_size):
    if reference is None or moving is None or affine is None:
        return [], [], []
    spacing = max(8, int(np.ceil(np.sqrt(np.count_nonzero(moving) / 192))))
    controls = []
    for y in range(spacing // 2, moving.shape[0], spacing):
        for x in range(spacing // 2, moving.shape[1], spacing):
            if not moving[y, x]:
                continue
            source = np.array([x, y]) * np.array(moving_size) / np.array(moving.shape[::-1])
            target = np.asarray(affine) @ np.r_[source, 1]
            tx, ty = np.rint(
                target * np.array(reference.shape[::-1]) / np.array(reference_size)
            ).astype(int)
            if 0 <= tx < reference.shape[1] and 0 <= ty < reference.shape[0] and reference[ty, tx]:
                controls.append(
                    {"moving": source.tolist(), "reference": target.tolist(), "errorPixels": 0.0}
                )
    unfiltered = _registration_triangles(controls)
    legacy = _registration_triangles(
        controls,
        moving_mask=moving,
        reference_mask=reference,
        moving_scale=moving.shape[1] / moving_size[0],
        reference_scale=reference.shape[1] / reference_size[0],
    )
    per_axis = _registration_triangles(
        controls,
        moving_mask=moving,
        reference_mask=reference,
        moving_scale=(moving.shape[1] / moving_size[0], moving.shape[0] / moving_size[1]),
        reference_scale=(
            reference.shape[1] / reference_size[0],
            reference.shape[0] / reference_size[1],
        ),
    )
    return unfiltered, legacy, per_axis


def mesh_signature(cells):
    return {tuple(sorted(tuple(np.round(point, 4)) for point in cell["moving"])) for cell in cells}


def covers(cells, point):
    try:
        map_registration_point({"triangles": cells}, *point)
        return True
    except AlignmentRejected:
        return False


def diagnose(manifest_path, campaign, output):
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    report = json.loads((campaign / "report.json").read_text())
    rows = []
    for row in report["rows"]:
        if row["recipe"] != "native-overview-v6" or row["kind"] != "positive":
            continue
        pair = manifest["pairs"][row["pairIndex"]]
        receipt = json.loads((campaign / "cache" / (row["digest"] + ".json")).read_text())
        if [_input_digest(pair[side]) for side in ("reference", "moving")] != receipt[
            "inputDigests"
        ]:
            raise ValueError("frozen diagnosis inputs differ from actual registration receipt")
        registration = receipt["registration"]
        cells = registration.get("triangles") or registration.get("overviewTriangles") or []
        masks = {side: variants(pair[side]) for side in ("reference", "moving")}
        mode = registration.get("evidence", {}).get("maskMode")
        selected = "prepared-thin" if mode == "thin-tissue-fallback" else "prepared-primary"
        if mode == "calibrated-fallback":
            selected = "prepared-calibrated"
            for side in masks:
                if masks[side][selected] is None:
                    masks[side][selected] = masks[side]["prepared-primary"]
        affine = registration.get("movingToReference")
        categories = Counter()
        source_states = Counter()
        target_states = Counter()
        projected_states = Counter()
        in_component_losses = Counter()
        unfiltered, reconstructed, per_axis = fixed_grid_meshes(
            masks["reference"][selected],
            masks["moving"][selected],
            affine,
            pair["reference"]["size"],
            pair["moving"]["size"],
        )
        reconstructed_matches = mesh_signature(reconstructed) == mesh_signature(cells)
        for landmark in pair["landmarks"]:
            if landmark.get("eligible") is not True:
                continue
            source = np.asarray(landmark["movingPoint"])
            try:
                map_registration_point({"triangles": cells}, *source)
                categories["supported-saved-map"] += 1
                continue
            except AlignmentRejected:
                pass
            if not cells or affine is None:
                categories["no-accepted-map-or-local-evidence"] += 1
                continue
            moving_mask = masks["moving"][selected]
            reference_mask = masks["reference"][selected]
            if moving_mask is None or reference_mask is None:
                categories["mask-selection-unresolved"] += 1
                continue
            projected = np.asarray(affine) @ np.r_[source, 1]
            moving_pixel = (
                source * np.array(moving_mask.shape[::-1]) / np.array(pair["moving"]["size"])
            )
            reference_pixel = (
                projected
                * np.array(reference_mask.shape[::-1])
                / np.array(pair["reference"]["size"])
            )
            reference_gt_pixel = (
                np.asarray(landmark["referencePoint"])
                * np.array(reference_mask.shape[::-1])
                / np.array(pair["reference"]["size"])
            )
            source_kind, target_kind = (
                point_kind(moving_mask, moving_pixel),
                point_kind(reference_mask, reference_gt_pixel),
            )
            projected_states[point_kind(reference_mask, reference_pixel)] += 1
            source_states[source_kind] += 1
            target_states[target_kind] += 1
            if "enclosed-background-mask-hole" in (source_kind, target_kind):
                categories["enclosed-background-hole-outside-supported-cells"] += 1
            elif source_kind != "tissue" or target_kind != "tissue":
                categories["outside-tissue-mask-or-frame"] += 1
            else:
                _, labels = cv2.connectedComponents((moving_mask > 0).astype(np.uint8))
                accepted_labels = set()
                for cell in cells:
                    center = (
                        np.mean(cell["moving"], axis=0)
                        * np.array(moving_mask.shape[::-1])
                        / np.array(pair["moving"]["size"])
                    )
                    x, y = np.rint(center).astype(int)
                    if 0 <= x < labels.shape[1] and 0 <= y < labels.shape[0]:
                        accepted_labels.add(int(labels[y, x]))
                x, y = np.rint(moving_pixel).astype(int)
                label = int(labels[y, x])
                categories[
                    "inside-accepted-component-outside-supported-grid-cells"
                    if label in accepted_labels
                    else "component-without-accepted-cells"
                ] += 1
                if label in accepted_labels:
                    in_component_losses[
                        "mask-cell-filtering"
                        if covers(unfiltered, source)
                        else "outside-paired-mask-grid-control-hull"
                    ] += 1
        rows.append(
            {
                "pairIndex": row["pairIndex"],
                "registrationDigest": row["digest"],
                "maskMode": mode,
                "maskSelectionScope": "preparation-branches-and-saved-mode-reconstruction",
                "landmarkSupportCategories": dict(categories),
                "inComponentUnsupportedDetail": dict(in_component_losses),
                "fixedGridReconstruction": {
                    "matchesSavedMovingCellTopology": reconstructed_matches,
                    "savedCells": len(cells),
                    "unfilteredCandidateCells": len(unfiltered),
                    "legacyScalarMaskFilteredCells": len(reconstructed),
                    "perAxisMaskFilteredCells": len(per_axis),
                    "scope": (
                        "same saved affine, masks and deterministic192-budget grid; "
                        "no fitting/promotion"
                    ),
                },
                "unsupportedSourceMaskStates": dict(source_states),
                "unsupportedPublishedReferenceMaskStates": dict(target_states),
                "unsupportedAffineProjectedReferenceMaskStates": dict(projected_states),
                "fixedTransformMaskDice": {
                    name: fixed_transform_dice(
                        masks["reference"][name],
                        masks["moving"][name],
                        affine,
                        pair["reference"]["size"],
                        pair["moving"]["size"],
                    )
                    if affine is not None
                    else None
                    for name in masks["reference"]
                },
            }
        )
    result = {
        "schema": "pathlab-frozen-support-diagnosis/1",
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "loadedOpenCvVersion": cv2.__version__,
        "scope": "saved-transform-and-mask-only; no fitting or gate changes; "
        "mask holes do not establish anatomical labels",
        "rows": rows,
        "totals": dict(sum((Counter(row["landmarkSupportCategories"]) for row in rows), Counter())),
    }
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.manifest, args.campaign, args.output)["totals"]))


if __name__ == "__main__":
    main()
