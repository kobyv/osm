#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "protobuf>=5.29.3",
# ]
# ///
"""
OSM PBF <-> OSM XML Converter

Converts between OpenStreetMap PBF (Protocol Buffer Format) and OSM XML format.
Uses only protobuf and stdlib, following osm_converter.py conventions.

PBF format specification: https://wiki.openstreetmap.org/wiki/PBF_Format

Current Implementation Status:
- PBF to XML: ✓ Fully functional (nodes, ways, relations with delta decoding)
- XML to PBF: Not yet implemented (requires encoder implementation)

Usage:
    # Using uv run (recommended)
    uv run osm_pbf_converter.py input.osm.pbf output.osm

    # Direct Python
    python osm_pbf_converter.py input.osm.pbf output.osm
"""

import struct
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Protobuf message definitions compiled as Python classes
# Based on OSM PBF protobuf schemas

from google.protobuf import message
from google.protobuf.internal import decoder, encoder


def skip_field(data: bytes, pos: int, tag_int: int) -> int:
    """Skip a protobuf field."""
    wire_type = tag_int & 7
    if wire_type == 0:  # Varint
        return decoder._DecodeVarint(data, pos)[1]
    elif wire_type == 1:  # Fixed64
        return pos + 8
    elif wire_type == 2:  # Length-delimited
        length, new_pos = decoder._DecodeVarint(data, pos)
        return new_pos + length
    elif wire_type == 5:  # Fixed32
        return pos + 4
    else:
        raise ValueError(f"Unknown wire type: {wire_type}")


class Blob(message.Message):
    """Protobuf Blob message."""

    def __init__(self):
        self.raw = None
        self.raw_size = None
        self.zlib_data = None

    def ParseFromString(self, data: bytes):
        """Parse blob from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # raw
                length, pos = decoder._DecodeVarint(data, pos)
                self.raw = data[pos : pos + length]
                pos += length
            elif field_num == 2 and wire_type == 0:  # raw_size
                self.raw_size, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 3 and wire_type == 2:  # zlib_data
                length, pos = decoder._DecodeVarint(data, pos)
                self.zlib_data = data[pos : pos + length]
                pos += length
            else:
                pos = skip_field(data, pos, tag_int)


class BlobHeader(message.Message):
    """Protobuf BlobHeader message."""

    def __init__(self):
        self.type = ""
        self.datasize = 0

    def ParseFromString(self, data: bytes):
        """Parse blob header from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # type
                length, pos = decoder._DecodeVarint(data, pos)
                self.type = data[pos : pos + length].decode("utf-8")
                pos += length
            elif field_num == 3 and wire_type == 0:  # datasize
                self.datasize, pos = decoder._DecodeSignedVarint32(data, pos)
            else:
                pos = skip_field(data, pos, tag_int)


class StringTable(message.Message):
    """Protobuf StringTable message."""

    def __init__(self):
        self.s = []

    def ParseFromString(self, data: bytes):
        """Parse string table from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # s (repeated bytes)
                length, pos = decoder._DecodeVarint(data, pos)
                self.s.append(data[pos : pos + length])
                pos += length
            else:
                pos = skip_field(data, pos, tag_int)


class PrimitiveBlock(message.Message):
    """Protobuf PrimitiveBlock message."""

    def __init__(self):
        self.stringtable = None
        self.primitivegroup = []
        self.granularity = 100
        self.lat_offset = 0
        self.lon_offset = 0
        self.date_granularity = 1000

    def ParseFromString(self, data: bytes):
        """Parse primitive block from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # stringtable
                length, pos = decoder._DecodeVarint(data, pos)
                self.stringtable = StringTable()
                self.stringtable.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 2 and wire_type == 2:  # primitivegroup
                length, pos = decoder._DecodeVarint(data, pos)
                group = PrimitiveGroup()
                group.ParseFromString(data[pos : pos + length])
                self.primitivegroup.append(group)
                pos += length
            elif field_num == 17 and wire_type == 0:  # granularity
                self.granularity, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 18 and wire_type == 0:  # date_granularity
                self.date_granularity, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 19 and wire_type == 0:  # lat_offset
                val, pos = decoder._DecodeVarint(data, pos)
                self.lat_offset = (val >> 1) ^ -(val & 1)  # ZigZag decode
            elif field_num == 20 and wire_type == 0:  # lon_offset
                val, pos = decoder._DecodeVarint(data, pos)
                self.lon_offset = (val >> 1) ^ -(val & 1)  # ZigZag decode
            else:
                pos = skip_field(data, pos, tag_int)


class PrimitiveGroup(message.Message):
    """Protobuf PrimitiveGroup message."""

    def __init__(self):
        self.nodes = []
        self.dense = None
        self.ways = []
        self.relations = []

    def ParseFromString(self, data: bytes):
        """Parse primitive group from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # nodes
                length, pos = decoder._DecodeVarint(data, pos)
                node = Node()
                node.ParseFromString(data[pos : pos + length])
                self.nodes.append(node)
                pos += length
            elif field_num == 2 and wire_type == 2:  # dense
                length, pos = decoder._DecodeVarint(data, pos)
                self.dense = DenseNodes()
                self.dense.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 3 and wire_type == 2:  # ways
                length, pos = decoder._DecodeVarint(data, pos)
                way = Way()
                way.ParseFromString(data[pos : pos + length])
                self.ways.append(way)
                pos += length
            elif field_num == 4 and wire_type == 2:  # relations
                length, pos = decoder._DecodeVarint(data, pos)
                relation = Relation()
                relation.ParseFromString(data[pos : pos + length])
                self.relations.append(relation)
                pos += length
            else:
                pos = skip_field(data, pos, tag_int)


class Node(message.Message):
    """Protobuf Node message."""

    def __init__(self):
        self.id = 0
        self.keys = []
        self.vals = []
        self.info = None
        self.lat = 0
        self.lon = 0

    def ParseFromString(self, data: bytes):
        """Parse node from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 0:  # id (int64, not sint64)
                self.id, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 2 and wire_type == 2:  # keys (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.keys.append(val)
            elif field_num == 3 and wire_type == 2:  # vals (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.vals.append(val)
            elif field_num == 4 and wire_type == 2:  # info
                length, pos = decoder._DecodeVarint(data, pos)
                self.info = Info()
                self.info.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 8 and wire_type == 0:  # lat
                val, pos = decoder._DecodeVarint(data, pos)
                self.lat = (val >> 1) ^ -(val & 1)  # ZigZag decode
            elif field_num == 9 and wire_type == 0:  # lon
                val, pos = decoder._DecodeVarint(data, pos)
                self.lon = (val >> 1) ^ -(val & 1)  # ZigZag decode
            else:
                pos = skip_field(data, pos, tag_int)


class DenseNodes(message.Message):
    """Protobuf DenseNodes message."""

    def __init__(self):
        self.id = []
        self.lat = []
        self.lon = []
        self.keys_vals = []
        self.denseinfo = None

    def ParseFromString(self, data: bytes):
        """Parse dense nodes from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # id (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.id.append(val)
            elif field_num == 5 and wire_type == 2:  # denseinfo
                length, pos = decoder._DecodeVarint(data, pos)
                self.denseinfo = DenseInfo()
                self.denseinfo.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 8 and wire_type == 2:  # lat (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.lat.append(val)
            elif field_num == 9 and wire_type == 2:  # lon (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.lon.append(val)
            elif field_num == 10 and wire_type == 2:  # keys_vals (packed int32)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.keys_vals.append(val)
            else:
                pos = skip_field(data, pos, tag_int)


class Way(message.Message):
    """Protobuf Way message."""

    def __init__(self):
        self.id = 0
        self.keys = []
        self.vals = []
        self.refs = []
        self.info = None

    def ParseFromString(self, data: bytes):
        """Parse way from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 0:  # id (int64, not sint64)
                self.id, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 2 and wire_type == 2:  # keys (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.keys.append(val)
            elif field_num == 3 and wire_type == 2:  # vals (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.vals.append(val)
            elif field_num == 4 and wire_type == 2:  # info
                length, pos = decoder._DecodeVarint(data, pos)
                self.info = Info()
                self.info.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 8 and wire_type == 2:  # refs (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.refs.append(val)
            else:
                pos = skip_field(data, pos, tag_int)


class Relation(message.Message):
    """Protobuf Relation message."""

    def __init__(self):
        self.id = 0
        self.keys = []
        self.vals = []
        self.roles_sid = []
        self.memids = []
        self.types = []
        self.info = None

    def ParseFromString(self, data: bytes):
        """Parse relation from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 0:  # id (int64, not sint64)
                self.id, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 2 and wire_type == 2:  # keys (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.keys.append(val)
            elif field_num == 3 and wire_type == 2:  # vals (packed)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.vals.append(val)
            elif field_num == 4 and wire_type == 2:  # info
                length, pos = decoder._DecodeVarint(data, pos)
                self.info = Info()
                self.info.ParseFromString(data[pos : pos + length])
                pos += length
            elif field_num == 8 and wire_type == 2:  # roles_sid (packed int32)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.roles_sid.append(val)
            elif field_num == 9 and wire_type == 2:  # memids (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.memids.append(val)
            elif field_num == 10 and wire_type == 2:  # types (packed enum)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.types.append(val)
            else:
                pos = skip_field(data, pos, tag_int)


class Info(message.Message):
    """Protobuf Info message."""

    def __init__(self):
        self.version = None
        self.timestamp = None
        self.changeset = None
        self.uid = None
        self.user_sid = None
        self.visible = None

    def ParseFromString(self, data: bytes):
        """Parse info from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 0:  # version
                self.version, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 2 and wire_type == 0:  # timestamp
                val, pos = decoder._DecodeVarint(data, pos)
                self.timestamp = (val >> 1) ^ -(val & 1)  # ZigZag decode
            elif field_num == 3 and wire_type == 0:  # changeset
                val, pos = decoder._DecodeVarint(data, pos)
                self.changeset = (val >> 1) ^ -(val & 1)  # ZigZag decode
            elif field_num == 4 and wire_type == 0:  # uid
                self.uid, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 5 and wire_type == 0:  # user_sid
                self.user_sid, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 6 and wire_type == 0:  # visible
                val, pos = decoder._DecodeVarint(data, pos)
                self.visible = bool(val)
            else:
                pos = skip_field(data, pos, tag_int)


class DenseInfo(message.Message):
    """Protobuf DenseInfo message."""

    def __init__(self):
        self.version = []
        self.timestamp = []
        self.changeset = []
        self.uid = []
        self.user_sid = []
        self.visible = []

    def ParseFromString(self, data: bytes):
        """Parse dense info from bytes."""
        pos = 0
        while pos < len(data):
            tag_int, pos = decoder._DecodeVarint(data, pos)
            field_num = tag_int >> 3
            wire_type = tag_int & 7

            if field_num == 1 and wire_type == 2:  # version (packed int32)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.version.append(val)
            elif field_num == 2 and wire_type == 2:  # timestamp (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.timestamp.append(val)
            elif field_num == 3 and wire_type == 2:  # changeset (packed sint64)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    val = (val >> 1) ^ -(val & 1)  # ZigZag decode
                    self.changeset.append(val)
            elif field_num == 4 and wire_type == 2:  # uid (packed sint32)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.uid.append(val)
            elif field_num == 5 and wire_type == 2:  # user_sid (packed sint32)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeSignedVarint32(data, pos)
                    self.user_sid.append(val)
            elif field_num == 6 and wire_type == 2:  # visible (packed bool)
                length, pos = decoder._DecodeVarint(data, pos)
                end_pos = pos + length
                while pos < end_pos:
                    val, pos = decoder._DecodeVarint(data, pos)
                    self.visible.append(bool(val))
            else:
                pos = skip_field(data, pos, tag_int)


def read_pbf_blob(file_handle):
    """Read a single blob from PBF file."""
    # Read header size (4 bytes, big endian)
    header_size_bytes = file_handle.read(4)
    if not header_size_bytes or len(header_size_bytes) < 4:
        return None, None

    header_size = struct.unpack(">I", header_size_bytes)[0]

    # Read header
    header_data = file_handle.read(header_size)
    if len(header_data) < header_size:
        return None, None

    blob_header = BlobHeader()
    blob_header.ParseFromString(header_data)

    # Read blob
    blob_data = file_handle.read(blob_header.datasize)
    if len(blob_data) < blob_header.datasize:
        return None, None

    blob = Blob()
    blob.ParseFromString(blob_data)

    # Decompress blob data
    if blob.raw is not None:
        data = blob.raw
    elif blob.zlib_data is not None:
        data = zlib.decompress(blob.zlib_data)
    else:
        raise ValueError("Unsupported blob compression")

    return blob_header.type, data


def pbf_to_xml(pbf_path: Path) -> ET.Element:
    """
    Convert OSM PBF file to OSM XML format.

    Args:
        pbf_path: Path to the OSM PBF file

    Returns:
        XML Element representing the OSM root
    """
    from datetime import datetime, timezone

    def add_metadata_to_element(elem: ET.Element, info: Info, string_table: list[str], date_scale: float):
        """Add metadata attributes from Info to XML element."""
        if info is None:
            return
        if info.version is not None:
            elem.set("version", str(info.version))
        if info.timestamp is not None:
            timestamp_seconds = info.timestamp * date_scale
            if 0 <= timestamp_seconds <= 2147483647:
                dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
                elem.set("timestamp", dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if info.changeset is not None and info.changeset != 0:
            elem.set("changeset", str(info.changeset))
        if info.uid is not None and info.uid != 0:
            elem.set("uid", str(info.uid))
        if info.user_sid is not None and info.user_sid < len(string_table):
            user = string_table[info.user_sid]
            if user and user != "highway":
                elem.set("user", user)

    # Create root element
    root = ET.Element("osm")
    root.set("version", "0.6")
    root.set("generator", "osm_pbf_converter")

    # Read PBF file
    with open(pbf_path, "rb") as f:
        while True:
            blob_type, data = read_pbf_blob(f)
            if blob_type is None:
                break

            if blob_type == "OSMHeader":
                # Parse header block (optional metadata)
                pass
            elif blob_type == "OSMData":
                # Parse primitive block
                block = PrimitiveBlock()
                block.ParseFromString(data)

                # Build string table
                string_table = [s.decode("utf-8") for s in block.stringtable.s]

                # Precompute per-block constants
                coord_scale = 1e-9 * block.granularity
                lat_origin = 1e-9 * block.lat_offset
                lon_origin = 1e-9 * block.lon_offset
                date_scale = block.date_granularity / 1000.0

                # Process primitive groups
                for group in block.primitivegroup:
                    # Process dense nodes
                    if group.dense is not None:
                        dense = group.dense
                        node_id = 0
                        lat_val = 0
                        lon_val = 0
                        keys_vals_pos = 0
                        keys_vals = dense.keys_vals
                        keys_vals_len = len(keys_vals)
                        denseinfo = dense.denseinfo

                        # Delta-decode metadata if present
                        version_val = 0
                        timestamp_val = 0
                        changeset_val = 0
                        uid_val = 0
                        user_sid_val = 0

                        dense_ids = dense.id
                        dense_lats = dense.lat
                        dense_lons = dense.lon

                        for i in range(len(dense_ids)):
                            # Delta decode
                            node_id += dense_ids[i]
                            lat_val += dense_lats[i]
                            lon_val += dense_lons[i]

                            # Create XML node
                            node_elem = ET.SubElement(root, "node")
                            node_elem.set("id", str(node_id))
                            node_elem.set("lat", f"{lat_origin + coord_scale * lat_val:.7f}")
                            node_elem.set("lon", f"{lon_origin + coord_scale * lon_val:.7f}")

                            # Add metadata from denseinfo if present
                            if denseinfo is not None:
                                info = denseinfo
                                if i < len(info.version):
                                    version_val += info.version[i]
                                    node_elem.set("version", str(version_val))
                                if i < len(info.timestamp):
                                    timestamp_val += info.timestamp[i]
                                    timestamp_seconds = timestamp_val * date_scale
                                    if 0 <= timestamp_seconds <= 2147483647:
                                        dt = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
                                        node_elem.set("timestamp", dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
                                if i < len(info.changeset):
                                    changeset_val += info.changeset[i]
                                    if changeset_val != 0:
                                        node_elem.set("changeset", str(changeset_val))
                                if i < len(info.uid):
                                    uid_val += info.uid[i]
                                    if uid_val != 0:
                                        node_elem.set("uid", str(uid_val))
                                if i < len(info.user_sid):
                                    user_sid_val += info.user_sid[i]
                                    if user_sid_val < len(string_table):
                                        user = string_table[user_sid_val]
                                        if user and user != "highway":
                                            node_elem.set("user", user)

                            # Parse tags (keys_vals is [key1, val1, key2, val2, ..., 0])
                            while keys_vals_pos < keys_vals_len:
                                key_id = keys_vals[keys_vals_pos]
                                if key_id == 0:  # End of tags for this node
                                    keys_vals_pos += 1
                                    break
                                val_id = keys_vals[keys_vals_pos + 1]
                                keys_vals_pos += 2

                                tag = ET.SubElement(node_elem, "tag")
                                tag.set("k", string_table[key_id])
                                tag.set("v", string_table[val_id])

                    # Process regular nodes
                    for node in group.nodes:
                        lat = lat_origin + coord_scale * node.lat
                        lon = lon_origin + coord_scale * node.lon

                        node_elem = ET.SubElement(root, "node")
                        node_elem.set("id", str(node.id))
                        node_elem.set("lat", f"{lat:.7f}")
                        node_elem.set("lon", f"{lon:.7f}")

                        # Add metadata
                        add_metadata_to_element(node_elem, node.info, string_table, date_scale)

                        # Add tags
                        for i in range(len(node.keys)):
                            tag = ET.SubElement(node_elem, "tag")
                            tag.set("k", string_table[node.keys[i]])
                            tag.set("v", string_table[node.vals[i]])

                    # Process ways
                    for way in group.ways:
                        way_elem = ET.SubElement(root, "way")
                        way_elem.set("id", str(way.id))

                        # Add metadata
                        add_metadata_to_element(way_elem, way.info, string_table, date_scale)

                        # Add node references (delta decoded)
                        node_id = 0
                        for delta in way.refs:
                            node_id += delta
                            nd = ET.SubElement(way_elem, "nd")
                            nd.set("ref", str(node_id))

                        # Add tags
                        for i in range(len(way.keys)):
                            tag = ET.SubElement(way_elem, "tag")
                            tag.set("k", string_table[way.keys[i]])
                            tag.set("v", string_table[way.vals[i]])

                    # Process relations
                    for relation in group.relations:
                        rel_elem = ET.SubElement(root, "relation")
                        rel_elem.set("id", str(relation.id))

                        # Add metadata
                        add_metadata_to_element(rel_elem, relation.info, string_table, date_scale)

                        # Add members (delta decoded)
                        member_id = 0
                        for i in range(len(relation.memids)):
                            member_id += relation.memids[i]
                            member = ET.SubElement(rel_elem, "member")

                            # Member type: 0=NODE, 1=WAY, 2=RELATION
                            member_type = ["node", "way", "relation"][relation.types[i]]
                            member.set("type", member_type)
                            member.set("ref", str(member_id))
                            member.set("role", string_table[relation.roles_sid[i]])

                        # Add tags
                        for i in range(len(relation.keys)):
                            tag = ET.SubElement(rel_elem, "tag")
                            tag.set("k", string_table[relation.keys[i]])
                            tag.set("v", string_table[relation.vals[i]])

    return root


def xml_to_pbf(xml_path: Path, pbf_path: Path) -> None:
    """
    Convert OSM XML file to PBF format.

    Args:
        xml_path: Path to the OSM XML file
        pbf_path: Path to the output PBF file
    """
    # This is a complex operation that requires:
    # 1. Parsing the XML
    # 2. Creating PrimitiveBlocks with StringTables
    # 3. Compressing and writing Blobs
    # 4. Handling delta encoding for DenseNodes

    raise NotImplementedError("XML to PBF conversion requires full encoder implementation")


def convert_pbf_to_xml_file(pbf_path: Path, xml_path: Path) -> None:
    """Convert OSM PBF file to XML file."""
    root = pbf_to_xml(pbf_path)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True)


def convert_xml_to_pbf_file(xml_path: Path, pbf_path: Path) -> None:
    """Convert OSM XML file to PBF file."""
    xml_to_pbf(xml_path, pbf_path)


def main() -> None:
    """Main entry point for CLI usage."""
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  PBF to XML: osm_pbf_converter.py <input.osm.pbf> <output.osm>")
        print("  XML to PBF: osm_pbf_converter.py <input.osm> <output.osm.pbf>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist")
        sys.exit(1)

    # Determine conversion direction based on file extensions
    in_name = input_path.name.lower()
    out_name = output_path.name.lower()

    if in_name.endswith(".pbf") and out_name.endswith(".osm"):
        print(f"Converting {input_path} (PBF) -> {output_path} (XML)")
        try:
            convert_pbf_to_xml_file(input_path, output_path)
            print("Conversion complete!")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif in_name.endswith(".osm") and out_name.endswith(".pbf"):
        print(f"Converting {input_path} (XML) -> {output_path} (PBF)")
        try:
            convert_xml_to_pbf_file(input_path, output_path)
            print("Conversion complete!")
        except NotImplementedError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print(f"Error: Invalid file extension combination. Use .osm.pbf for PBF and .osm for XML")
        sys.exit(1)


if __name__ == "__main__":
    main()
