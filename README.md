# icc-wcs-vcgt

This is a simple Python script to fix calibration ICC profiles generated
in Windows to use in GNU/Linux.

Windows stores calibration data in WCS tag which GNU tools such as colord
and xcalib do not understand. This tool converts this data to the format that
they can understand.
