# Generate bounded OME-Zarr exchange derivatives only

PathLab will generate and independently validate immutable Exchange Representations against OME-Zarr specification revision 0.5.2 on Zarr v3, with wire `ome.version` `"0.5"`, but will not admit arbitrary OME-Zarr as an authoritative source in v1. The profile is limited to one calibrated `uint8` two-dimensional RGB multiscale image and excludes remote references, labels, tables, high-content screening, custom transforms, and experimental specification versions so interoperability never becomes an ambiguous conversion claim.
