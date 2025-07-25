#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Convert WCS calibration information to VCGT."""


import argparse
import sys
import struct
import xml.etree.ElementTree as ET


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Convert WCS calibration information to VCGT")
    parser.add_argument("input_file",
                        help="Input profile",
                        type=str)
    parser.add_argument("output_file",
                        help="Output profile",
                        type=str)
    return parser.parse_args()


def check_signature(prof_data: bytes) -> bool:
    """Check profile signature."""
    prof_size, \
        prof_ver, \
        prof_dev, \
        prof_col, \
        prof_sig, \
        prof_plat, \
        prof_creator = struct.unpack_from(
            ">I4xI4s4s16x4s4s36x4s", prof_data, 0)
    # Basic ICC header checks
    if prof_size != len(prof_data):
        return False
    if prof_size % 4 != 0:
        return False
    if prof_sig != b"acsp":
        return False
    if prof_ver > 0x04400000:
        return False
    # Only for monitor ICC
    if prof_dev != b"mntr":
        return False
    if prof_col != b"RGB ":
        return False
    # WCS profiles
    if prof_plat != b"MSFT":
        return False
    if prof_creator != b"MSFT":
        return False
    return True


def parse_tags(prof_data: bytes) -> dict:
    """Parse ICC tags."""
    tag_count = struct.unpack_from(">I", prof_data, 128)[0]
    result = {}
    for i in range(tag_count):
        tag_sig, \
            tag_offset, \
            tag_size = struct.unpack_from(">4sII", prof_data, 132 + 12 * i)
        result[tag_sig] = prof_data[tag_offset:tag_offset+tag_size]
    return result


def parse_wcs(wcs_data: bytes) -> tuple:
    """Parse WCS tag"""
    tag_sig, \
        cdmp_ofs, \
        cdmp_size, \
        camp_ofs, \
        camp_size, \
        gmmp_ofs, \
        gmmp_size = struct.unpack_from(">4s4xIIIIII", wcs_data, 0)
    assert tag_sig == b"MS10", "Failed to parse WCS profile tag"
    cdmp_data = wcs_data[cdmp_ofs:cdmp_ofs+cdmp_size]
    camp_data = wcs_data[camp_ofs:camp_ofs+camp_size]
    gmmp_data = wcs_data[gmmp_ofs:gmmp_ofs+gmmp_size]
    return cdmp_data, camp_data, gmmp_data


def extract_calib_data(cdmp_data: bytes) -> dict:
    """Extract calibration data from WCS ColorDeviceModel data"""
    cdmp_root = ET.fromstring(cdmp_data.decode("utf16"))
    ns = {
        "cdm": "http://schemas.microsoft.com/windows/2005/02/color/ColorDeviceModel",
        "cal": "http://schemas.microsoft.com/windows/2007/11/color/Calibration",
        "wcs": "http://schemas.microsoft.com/windows/2005/02/color/WcsCommonProfileTypes",
    }
    calib_data_tag = cdmp_root.find(
        "cdm:Calibration/" +
        "cal:AdapterGammaConfiguration/" +
        "cal:ParameterizedCurves", ns)
    assert calib_data_tag is not None
    calib_data = {}
    for i, tag in zip(["r", "g", "b"],
                      ["wcs:RedTRC", "wcs:GreenTRC", "wcs:BlueTRC"]):
        calib_tag = calib_data_tag.find(tag, ns)
        if calib_tag is None:
            calib_tag = {}
        else:
            assert len(set(calib_tag.attrib.keys()).difference(
                ["Gamma", "Gain", "Offset1"])) == 0
        calib_data[i] = tuple(
            float(calib_tag.get(x, d))
            for x, d in [("Gamma", 1), ("Offset1", 0), ("Gain", 1)]
        )
    return calib_data


def generate_vcgt(calib_data: dict) -> bytes:
    """Generate parametrized VCGT."""
    data = b"vcgt\0\0\0\0\0\0\0\1"
    for i in ["r", "g", "b"]:
        for v in calib_data[i]:
            data += struct.pack(">I", int(v * 65535))
    return data


def generate_body(tags: dict) -> bytes:
    """Generate ICC profile body."""
    data = struct.pack(">I", len(tags))
    offset = 132 + len(tags) * 12
    for tag, val in tags.items():
        data += struct.pack(">4sII", tag, offset, len(val))
        size = len(val) + 3
        size -= size % 4
        offset += size
    for val in tags.values():
        data += val
        pad_size = 4 - len(val) % 4
        if pad_size < 4:
            data += b'\0' * pad_size
    return data


def create_profile(header: bytes, body: bytes) -> bytes:
    """Combine ICC body and header."""
    return struct.pack(">I", len(body) + 128) + header[4:] + body


def main(input_file: str, output_file: str) -> int:
    """Main function."""

    with open(input_file, "rb") as f:
        prof_data = f.read()
    if not check_signature(prof_data):
        print("Invalid ICC profile")
        return 1
    tags = parse_tags(prof_data)
    if b"vcgt" in tags:
        print("Profile already has VCGT")
        return 1
    wcs_data = tags.get(b"MS00")
    if wcs_data is None:
        print("WCS tag is not present")
        return 1
    cdmp_data, _, _ = parse_wcs(wcs_data)
    calib_data = extract_calib_data(cdmp_data)
    tags[b"vcgt"] = generate_vcgt(calib_data)
    with open(output_file, "wb") as f:
        f.write(create_profile(prof_data[:128], generate_body(tags)))
    return 0


if __name__ == "__main__":
    sys.exit(main(**vars(parse_args())))
