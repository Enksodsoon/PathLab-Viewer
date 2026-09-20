# Open-source registration integration

PathLab keeps its default registration worker CPU-only and bounded to the
existing DZI pyramid. The worker stores coordinate maps and never creates a
second warped slide pyramid.

## Adopted methods

- **VALIS:** component masks, coarse-to-fine registration, groupwise slide
  ordering concepts, and higher-resolution local checks. The default worker
  implements these ideas with NumPy and OpenCV rather than depending on the
  full VALIS runtime.
- **HISAlign:** optical-density preprocessing, KAZE candidate identity
  evidence, serializable coordinate maps, and explicit forward/reverse
  consistency checks. KAZE evidence can distinguish candidate fragments only
  after coarse alignment and local structural support; it cannot promote a
  pair by itself.
- **wsireg:** explicit anchors and transform composition through the chosen
  coordinate reference. PathLab persists the composed result in an immutable
  registration revision.
- **Warpy:** viewer-side navigation through saved transforms. Display pixels
  remain native slide tiles; maps move the viewport and crosshair.

## Dependency decision

VALIS and HISAlign are MIT licensed, wsireg is MIT licensed, and Warpy is
Apache-2.0 licensed. Their complete runtimes are not default dependencies:
VALIS and HISAlign include Torch, SimpleITK, and other large packages; wsireg
uses ITK-Elastix; Warpy runs in the QuPath/Java environment. Adding those
runtimes to the web worker would conflict with the lightweight 2 GiB process
target and increase deployment and security maintenance.

The optical-density/KAZE implementation is PathLab-authored against public
algorithm descriptions and OpenCV APIs. No upstream source file is vendored.
Upstream projects remain useful benchmark engines and design references:

- https://github.com/MathOnco/valis
- https://github.com/yifanfeng97/hisalign
- https://github.com/NHPatterson/wsireg
- https://github.com/BIOP/qupath-extension-warpy

## Claim boundary

Feature inliers, flow-cycle error, patch correlation, and fragment layout are
engineering evidence. They do not establish anatomical accuracy. A pair is
qualified only after independent landmarks measure the saved coordinate map;
ambiguous and unsupported regions remain approximate or rejected.
