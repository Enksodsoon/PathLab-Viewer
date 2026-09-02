# Require static DZI before browser publication

Every active Publication must reference an integrity-verified static DZI Browser Representation that the Resident Control Plane can authorize and Caddy can serve in any non-maintenance mode. Direct OME dynamic tiles, source decoding, conversion, and OME-Zarr or DICOM generation run only during an Imaging Mode Reservation and queue otherwise; an unpublished or unconverted source remains private, and downloading an original WSI to the browser is prohibited as a fallback.
