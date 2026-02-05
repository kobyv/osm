#!/usr/bin/env python3
"""
OSM XML <-> OSM JSON <-> Level0L <-> GeoJSON Converter

Converts between JOSM-compatible OSM XML format, OSM JSON format, Level0L format, and GeoJSON format.
Numeric conversions: id, version, uid, changeset (int), lat, lon (float), nodes (int array).
All other attributes default to strings.
"""

import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TypedDict, NotRequired, Any


class OSMNode(TypedDict):
    """OSM node element in JSON format."""

    type: str  # Always "node"
    id: int
    lat: float
    lon: float
    tags: NotRequired[dict[str, str]]
    # Optional OSM metadata
    version: NotRequired[int]
    timestamp: NotRequired[str]
    changeset: NotRequired[int]
    uid: NotRequired[int]
    user: NotRequired[str]


class OSMWay(TypedDict):
    """OSM way element in JSON format."""

    type: str  # Always "way"
    id: int
    nodes: NotRequired[list[int]]
    tags: NotRequired[dict[str, str]]
    # Optional OSM metadata
    version: NotRequired[int]
    timestamp: NotRequired[str]
    changeset: NotRequired[int]
    uid: NotRequired[int]
    user: NotRequired[str]


class OSMMember(TypedDict):
    """Member of an OSM relation."""

    type: str
    ref: int
    role: NotRequired[str]


class OSMRelation(TypedDict):
    """OSM relation element in JSON format."""

    type: str  # Always "relation"
    id: int
    members: NotRequired[list[OSMMember]]
    tags: NotRequired[dict[str, str]]
    # Optional OSM metadata
    version: NotRequired[int]
    timestamp: NotRequired[str]
    changeset: NotRequired[int]
    uid: NotRequired[int]
    user: NotRequired[str]


# Union type for any OSM element
OSMElement = OSMNode | OSMWay | OSMRelation


class OSMData(TypedDict):
    """OSM JSON data structure."""

    version: str
    generator: str
    elements: list[OSMElement]
    # Optional fields
    copyright: NotRequired[str]
    attribution: NotRequired[str]
    license: NotRequired[str]


def osm_xml_to_json(xml_path: Path) -> OSMData:
    """
    Convert OSM XML file to OSM JSON format.

    Args:
        xml_path: Path to the OSM XML file

    Returns:
        Dictionary representing the OSM JSON structure
    """
    # Define which attributes should be converted to numbers
    FLOAT_ATTRS = {"lat", "lon"}
    INT_ATTRS = {"id", "version", "uid", "changeset"}

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Build the base JSON structure
    result: dict[str, str | list[OSMElement]] = {
        "version": root.get("version", "0.6"),
        "generator": root.get("generator", "osm_converter"),
    }

    # Add optional metadata from note/meta elements
    note_elem = root.find("note")
    if note_elem is not None and note_elem.text:
        result["copyright"] = "OpenStreetMap and contributors"
        result["attribution"] = "http://www.openstreetmap.org/copyright"
        result["license"] = "http://opendatacommons.org/licenses/odbl/1-0/"

    elements: list[OSMElement] = []

    # Process nodes
    for node in root.findall("node"):
        node_element: dict[str, int | float | str | dict[str, str]] = {"type": "node"}

        # Process all attributes generically
        for attr_name, attr_value in node.attrib.items():
            if attr_name in INT_ATTRS:
                node_element[attr_name] = int(attr_value)
            elif attr_name in FLOAT_ATTRS:
                node_element[attr_name] = float(attr_value)
            else:
                # Default to string
                node_element[attr_name] = attr_value

        # Process tags
        tags: dict[str, str] = {}
        for tag in node.findall("tag"):
            k = tag.get("k")
            v = tag.get("v")
            if k is not None and v is not None:
                tags[k] = v
        if tags:
            node_element["tags"] = tags

        elements.append(node_element)  # type: ignore[arg-type]

    # Process ways
    for way in root.findall("way"):
        way_element: dict[str, int | float | str | list[int] | dict[str, str]] = {"type": "way"}

        # Process all attributes generically
        for attr_name, attr_value in way.attrib.items():
            if attr_name in INT_ATTRS:
                way_element[attr_name] = int(attr_value)
            elif attr_name in FLOAT_ATTRS:
                way_element[attr_name] = float(attr_value)
            else:
                # Default to string
                way_element[attr_name] = attr_value

        # Process node references (kept as list of integers)
        nodes: list[int] = []
        for nd in way.findall("nd"):
            ref = nd.get("ref")
            if ref is not None:
                nodes.append(int(ref))
        if nodes:
            way_element["nodes"] = nodes

        # Process tags
        tags = {}
        for tag in way.findall("tag"):
            k = tag.get("k")
            v = tag.get("v")
            if k is not None and v is not None:
                tags[k] = v
        if tags:
            way_element["tags"] = tags

        elements.append(way_element)  # type: ignore[arg-type]

    # Process relations
    for relation in root.findall("relation"):
        relation_element: dict[str, int | float | str | list[dict[str, int | str]] | dict[str, str]] = {
            "type": "relation"
        }

        # Process all attributes generically
        for attr_name, attr_value in relation.attrib.items():
            if attr_name in INT_ATTRS:
                relation_element[attr_name] = int(attr_value)
            elif attr_name in FLOAT_ATTRS:
                relation_element[attr_name] = float(attr_value)
            else:
                # Default to string
                relation_element[attr_name] = attr_value

        # Process members
        members: list[dict[str, int | str]] = []
        for member in relation.findall("member"):
            member_data: dict[str, int | str] = {}
            for attr_name, attr_value in member.attrib.items():
                if attr_name == "ref":
                    member_data[attr_name] = int(attr_value)
                else:
                    member_data[attr_name] = attr_value
            members.append(member_data)
        if members:
            relation_element["members"] = members  # type: ignore[assignment]

        # Process tags
        tags = {}
        for tag in relation.findall("tag"):
            k = tag.get("k")
            v = tag.get("v")
            if k is not None and v is not None:
                tags[k] = v
        if tags:
            relation_element["tags"] = tags

        elements.append(relation_element)  # type: ignore[arg-type]

    result["elements"] = elements
    return result  # type: ignore[return-value]


def osm_json_to_xml(json_path: Path) -> ET.Element:
    """
    Convert OSM JSON file to OSM XML format.

    Args:
        json_path: Path to the OSM JSON file

    Returns:
        XML Element representing the OSM root
    """
    # Keys that should not be treated as XML attributes
    SPECIAL_KEYS = {"type", "tags", "nodes", "members"}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Create root element
    root = ET.Element("osm")
    root.set("version", str(data.get("version", "0.6")))
    root.set("generator", str(data.get("generator", "osm_converter")))

    # Add note if copyright info exists
    if "copyright" in data:
        note = ET.SubElement(root, "note")
        note.text = "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."

    # Add meta if present
    meta = ET.SubElement(root, "meta")
    meta.set("osm_base", "2026-01-31T00:00:00Z")

    # Process elements
    for element in data.get("elements", []):
        elem_type = element["type"]

        if elem_type == "node":
            node = ET.SubElement(root, "node")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    node.set(key, str(value))

            # Add tags
            for key, value in element.get("tags", {}).items():
                tag = ET.SubElement(node, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "way":
            way = ET.SubElement(root, "way")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    way.set(key, str(value))

            # Add node references
            for node_ref in element.get("nodes", []):  # type: ignore[attr-defined]
                nd = ET.SubElement(way, "nd")
                nd.set("ref", str(node_ref))

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(way, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "relation":
            relation = ET.SubElement(root, "relation")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    relation.set(key, str(value))

            # Add members
            for member_data in element.get("members", []):  # type: ignore[attr-defined]
                member = ET.SubElement(relation, "member")
                # Add all member attributes generically
                for key, value in member_data.items():
                    member.set(key, str(value))

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(relation, "tag")
                tag.set("k", key)
                tag.set("v", value)

    return root


def convert_xml_to_json_file(xml_path: Path, json_path: Path) -> None:
    """Convert OSM XML file to JSON file."""
    data = osm_xml_to_json(xml_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def convert_json_to_xml_file(json_path: Path, xml_path: Path) -> None:
    """Convert OSM JSON file to XML file."""
    root = osm_json_to_xml(json_path)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True)


def osm_json_to_l0l(json_data: OSMData) -> str:
    """
    Convert OSM JSON data to Level0L format string.

    Args:
        json_data: Dictionary representing the OSM JSON structure

    Returns:
        String in Level0L format
    """
    lines: list[str] = []

    for element in json_data.get("elements", []):
        elem_type = element["type"]
        has_properties = False

        if elem_type == "node":
            # Node header: node <id>: <lat>, <lon>
            node_id = element["id"]
            lat = element.get("lat", 0.0)
            lon = element.get("lon", 0.0)
            lines.append(f"node {node_id}: {lat:.7f}, {lon:.7f}")

            # Add tags
            for key, value in element.get("tags", {}).items():
                lines.append(f"  {key} = {value}")
                has_properties = True

        elif elem_type == "way":
            # Way header: way <id>
            way_id = element["id"]
            lines.append(f"way {way_id}")

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                lines.append(f"  {key} = {value}")
                has_properties = True

            # Add node references
            for node_ref in element.get("nodes", []):  # type: ignore[attr-defined]
                lines.append(f"  nd {node_ref}")
                has_properties = True

        elif elem_type == "relation":
            # Relation header: relation <id>
            relation_id = element["id"]
            lines.append(f"relation {relation_id}")

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                lines.append(f"  {key} = {value}")
                has_properties = True

            # Add members
            for member in element.get("members", []):  # type: ignore[attr-defined]
                member_type = member.get("type", "")
                member_ref = member.get("ref", 0)
                member_role = member.get("role", "")
                lines.append(f"  member {member_type} {member_ref} {member_role}")
                has_properties = True

        # Add blank line between elements only if properties exist
        if has_properties:
            lines.append("")

    return "\n".join(lines)


def osm_l0l_to_json(l0l_content: str) -> OSMData:
    """
    Convert Level0L format string to OSM JSON data.

    Args:
        l0l_content: String in Level0L format

    Returns:
        Dictionary representing the OSM JSON structure
    """
    elements: list[OSMElement] = []

    lines = l0l_content.strip().split("\n")
    current_element: dict[str, int | float | str | list[int] | list[dict[str, int | str]] | dict[str, str]] | None = (
        None
    )

    for line in lines:
        # Skip empty lines
        if not line.strip():
            if current_element is not None:
                elements.append(current_element)  # type: ignore[arg-type]
                current_element = None
            continue

        # Check if line is indented (tag or node reference)
        if line.startswith("  "):
            if current_element is None:
                continue

            content = line.strip()

            # Node reference in way: "nd <ref>"
            if content.startswith("nd "):
                ref = int(content.split()[1])
                if "nodes" not in current_element:
                    current_element["nodes"] = []
                nodes_list = current_element["nodes"]
                assert isinstance(nodes_list, list)
                nodes_list.append(ref)  # type: ignore[arg-type]

            # Member in relation: "member <type> <ref> <role>"
            elif content.startswith("member "):
                parts = content.split(maxsplit=3)
                member: dict[str, int | str] = {
                    "type": parts[1],
                    "ref": int(parts[2]),
                }
                if len(parts) > 3:
                    member["role"] = parts[3]
                if "members" not in current_element:
                    current_element["members"] = []
                members_list = current_element["members"]
                assert isinstance(members_list, list)
                members_list.append(member)  # type: ignore[arg-type]

            # Tag: "key = value"
            elif " = " in content:
                key, value = content.split(" = ", 1)
                if "tags" not in current_element:
                    current_element["tags"] = {}
                tags_dict = current_element["tags"]
                assert isinstance(tags_dict, dict)
                tags_dict[key] = value

        # Element header
        else:
            # Save previous element
            if current_element is not None:
                elements.append(current_element)  # type: ignore[arg-type]

            # Parse new element header
            if line.startswith("node "):
                # node <id>: <lat>, <lon>
                parts = line.split(":", 1)
                node_id = int(parts[0].split()[1])
                coords = parts[1].strip().split(",")
                lat = float(coords[0].strip())
                lon = float(coords[1].strip())

                current_element = {
                    "type": "node",
                    "id": node_id,
                    "lat": lat,
                    "lon": lon,
                }

            elif line.startswith("way "):
                # way <id>
                way_id = int(line.split()[1])
                current_element = {
                    "type": "way",
                    "id": way_id,
                }

            elif line.startswith("relation "):
                # relation <id>
                relation_id = int(line.split()[1])
                current_element = {
                    "type": "relation",
                    "id": relation_id,
                }

    # Don't forget the last element
    if current_element is not None:
        elements.append(current_element)  # type: ignore[arg-type]

    return {  # type: ignore[return-value]
        "version": "0.6",
        "generator": "osm_converter",
        "elements": elements,
    }


def convert_json_to_l0l_file(json_path: Path, l0l_path: Path) -> None:
    """Convert OSM JSON file to Level0L file."""
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    l0l_content = osm_json_to_l0l(json_data)
    with open(l0l_path, "w", encoding="utf-8") as f:
        f.write(l0l_content)


def convert_l0l_to_json_file(l0l_path: Path, json_path: Path) -> None:
    """Convert Level0L file to OSM JSON file."""
    with open(l0l_path, "r", encoding="utf-8") as f:
        l0l_content = f.read()
    json_data = osm_l0l_to_json(l0l_content)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)


def convert_xml_to_l0l_file(xml_path: Path, l0l_path: Path) -> None:
    """Convert OSM XML file to Level0L file."""
    json_data = osm_xml_to_json(xml_path)
    l0l_content = osm_json_to_l0l(json_data)
    with open(l0l_path, "w", encoding="utf-8") as f:
        f.write(l0l_content)


def convert_l0l_to_xml_file(l0l_path: Path, xml_path: Path) -> None:
    """Convert Level0L file to OSM XML file."""
    with open(l0l_path, "r", encoding="utf-8") as f:
        l0l_content = f.read()
    json_data = osm_l0l_to_json(l0l_content)
    root = osm_json_to_xml_from_data(json_data)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True)


def osm_json_to_xml_from_data(data: OSMData) -> ET.Element:
    """
    Convert OSM JSON data (already loaded) to OSM XML format.

    Args:
        data: Dictionary representing the OSM JSON structure

    Returns:
        XML Element representing the OSM root
    """
    # Keys that should not be treated as XML attributes
    SPECIAL_KEYS = {"type", "tags", "nodes", "members"}

    # Create root element
    root = ET.Element("osm")
    root.set("version", str(data.get("version", "0.6")))
    root.set("generator", str(data.get("generator", "osm_converter")))

    # Add note if copyright info exists
    if "copyright" in data:
        note = ET.SubElement(root, "note")
        note.text = "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."

    # Add meta if present
    meta = ET.SubElement(root, "meta")
    meta.set("osm_base", "2026-01-31T00:00:00Z")

    # Process elements
    for element in data.get("elements", []):
        elem_type = element["type"]

        if elem_type == "node":
            node = ET.SubElement(root, "node")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    node.set(key, str(value))

            # Add tags
            for key, value in element.get("tags", {}).items():
                tag = ET.SubElement(node, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "way":
            way = ET.SubElement(root, "way")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    way.set(key, str(value))

            # Add node references
            for node_ref in element.get("nodes", []):  # type: ignore[attr-defined]
                nd = ET.SubElement(way, "nd")
                nd.set("ref", str(node_ref))

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(way, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "relation":
            relation = ET.SubElement(root, "relation")

            # Add all attributes generically (except special keys)
            for key, value in element.items():
                if key not in SPECIAL_KEYS:
                    relation.set(key, str(value))

            # Add members
            for member_data in element.get("members", []):  # type: ignore[attr-defined]
                member = ET.SubElement(relation, "member")
                # Add all member attributes generically
                for key, value in member_data.items():
                    member.set(key, str(value))

            # Add tags
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(relation, "tag")
                tag.set("k", key)
                tag.set("v", value)

    return root


def osm_json_to_osmchange(json_data: OSMData) -> ET.Element:
    """
    Convert OSM JSON data (JOSM format) to OsmChange XML format.

    Args:
        json_data: Dictionary representing the OSM JSON structure with JOSM extensions
                  (action attributes for elements)

    Returns:
        XML Element representing the OsmChange root

    Raises:
        ValueError: If elements are missing required changeset/version attributes
    """
    # Keys that should not be treated as XML attributes
    SPECIAL_KEYS = {"type", "tags", "nodes", "members", "action"}
    # Keys that should be filtered out from OsmChange output
    FILTERED_KEYS = {"timestamp", "uid", "user", "visible"}

    # Create root element
    root = ET.Element("osmChange")
    root.set("version", str(json_data.get("version", "0.6")))
    root.set("generator", str(json_data.get("generator", "osm_converter")))

    # Organize elements by action
    create_elements: list[OSMElement] = []
    modify_elements: list[OSMElement] = []
    delete_elements: list[OSMElement] = []

    for element in json_data.get("elements", []):
        elem_id = element.get("id", 0)
        action = element.get("action", "")  # type: ignore[attr-defined]

        # Validate changeset and version requirements
        # Exception: Negative IDs (new objects) don't require changeset/version
        if elem_id < 0:
            # New object being created
            create_elements.append(element)
        elif action == "delete":
            # Deleted object - must have changeset and version
            if "changeset" not in element or "version" not in element:
                raise ValueError(
                    f"Element with id={elem_id} and action='delete' is missing required 'changeset' or 'version' attribute"
                )
            delete_elements.append(element)
        elif action == "modify":
            # Modified object - must have changeset and version
            if "changeset" not in element or "version" not in element:
                raise ValueError(
                    f"Element with id={elem_id} and action='modify' is missing required 'changeset' or 'version' attribute"
                )
            modify_elements.append(element)
        # Skip elements with no action and positive ID (unchanged data from server)

    # Helper function to add an element to a parent
    def add_element_to_parent(parent: ET.Element, element: OSMElement) -> None:
        elem_type = element["type"]
        # Combine special keys and filtered keys
        excluded_keys = SPECIAL_KEYS | FILTERED_KEYS

        if elem_type == "node":
            node = ET.SubElement(parent, "node")
            for key, value in element.items():
                if key not in excluded_keys:
                    node.set(key, str(value))
            for key, value in element.get("tags", {}).items():
                tag = ET.SubElement(node, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "way":
            way = ET.SubElement(parent, "way")
            for key, value in element.items():
                if key not in excluded_keys:
                    way.set(key, str(value))
            for node_ref in element.get("nodes", []):  # type: ignore[attr-defined]
                nd = ET.SubElement(way, "nd")
                nd.set("ref", str(node_ref))
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(way, "tag")
                tag.set("k", key)
                tag.set("v", value)

        elif elem_type == "relation":
            relation = ET.SubElement(parent, "relation")
            for key, value in element.items():
                if key not in excluded_keys:
                    relation.set(key, str(value))
            for member_data in element.get("members", []):  # type: ignore[attr-defined]
                member = ET.SubElement(relation, "member")
                for key, value in member_data.items():
                    member.set(key, str(value))
            for key, value in element.get("tags", {}).items():  # type: ignore[attr-defined]
                tag = ET.SubElement(relation, "tag")
                tag.set("k", key)
                tag.set("v", value)

    # Add create block if there are elements to create
    if create_elements:
        create_block = ET.SubElement(root, "create")
        for element in create_elements:
            add_element_to_parent(create_block, element)

    # Add modify block if there are elements to modify
    if modify_elements:
        modify_block = ET.SubElement(root, "modify")
        for element in modify_elements:
            add_element_to_parent(modify_block, element)

    # Add delete block if there are elements to delete
    if delete_elements:
        delete_block = ET.SubElement(root, "delete")
        for element in delete_elements:
            add_element_to_parent(delete_block, element)

    return root


def convert_json_to_osmchange_file(json_path: Path, osc_path: Path) -> None:
    """Convert OSM JSON file (JOSM format) to OsmChange file."""
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    root = osm_json_to_osmchange(json_data)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(osc_path), encoding="UTF-8", xml_declaration=True)


def convert_xml_to_osmchange_file(xml_path: Path, osc_path: Path) -> None:
    """Convert OSM XML file (JOSM format) to OsmChange file."""
    json_data = osm_xml_to_json(xml_path)
    root = osm_json_to_osmchange(json_data)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(osc_path), encoding="UTF-8", xml_declaration=True)


def osm_json_to_geojson(json_data: OSMData) -> dict[str, Any]:
    """
    Convert OSM JSON data to GeoJSON format.

    Args:
        json_data: Dictionary representing the OSM JSON structure

    Returns:
        Dictionary representing the GeoJSON FeatureCollection
    """
    features: list[dict[str, Any]] = []

    # Build a lookup for nodes to get coordinates
    node_coords: dict[int, tuple[float, float]] = {}
    for element in json_data.get("elements", []):
        if element["type"] == "node":
            node_id = element["id"]
            lat = element.get("lat", 0.0)
            lon = element.get("lon", 0.0)
            node_coords[node_id] = (lon, lat)  # GeoJSON uses [lon, lat] order

    # Process each element
    for element in json_data.get("elements", []):
        elem_type = element["type"]
        elem_id = element["id"]

        # Build properties from tags and metadata
        properties: dict[str, Any] = {}

        # Add @id property
        properties["@id"] = f"{elem_type}/{elem_id}"

        # Add regular tags (not metadata)
        for key, value in element.get("tags", {}).items():
            properties[key] = value

        # Add metadata with @ prefix
        metadata_keys = ["timestamp", "version", "changeset", "user", "uid"]
        for key in metadata_keys:
            if key in element:
                properties[f"@{key}"] = element[key]

        # Create geometry and feature based on element type
        if elem_type == "node":
            lat = element.get("lat", 0.0)
            lon = element.get("lon", 0.0)
            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "id": f"node/{elem_id}",
            }
            features.append(feature)

        elif elem_type == "way":
            nodes = element.get("nodes", [])  # type: ignore[attr-defined]
            if not nodes:
                continue

            # Get coordinates for all nodes in the way
            coordinates = []
            for node_ref in nodes:  # type: ignore[attr-defined]
                if node_ref in node_coords:
                    coordinates.append(list(node_coords[node_ref]))

            if not coordinates:
                continue

            # Determine if way is closed (first and last node are the same)
            is_closed = len(nodes) > 1 and nodes[0] == nodes[-1]  # type: ignore[arg-type,index]

            if is_closed:
                # Closed way → Polygon
                geometry = {"type": "Polygon", "coordinates": [coordinates]}
            else:
                # Open way → LineString
                geometry = {"type": "LineString", "coordinates": coordinates}

            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
                "id": f"way/{elem_id}",
            }
            features.append(feature)

        elif elem_type == "relation":
            # For relations, we create a simple feature with the tags
            # Full relation geometry reconstruction would require way data
            # This is a simplified representation
            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": None,  # Relations need complex geometry processing
                "id": f"relation/{elem_id}",
            }
            features.append(feature)

    # Build GeoJSON FeatureCollection
    geojson: dict[str, Any] = {
        "type": "FeatureCollection",
        "generator": json_data.get("generator", "osm_converter"),
        "features": features,
    }

    # Add optional metadata
    if "copyright" in json_data:
        geojson["copyright"] = json_data["copyright"]

    return geojson


def geojson_to_osm_json(geojson_data: dict[str, Any]) -> OSMData:
    """
    Convert GeoJSON FeatureCollection to OSM JSON format.

    Args:
        geojson_data: Dictionary representing the GeoJSON FeatureCollection

    Returns:
        Dictionary representing the OSM JSON structure
    """
    elements: list[OSMElement] = []
    node_id_counter = 1

    # First pass: create nodes from Point geometries and collect way node references
    node_map: dict[tuple[float, float], int] = {}  # (lon, lat) -> node_id

    for feature in geojson_data.get("features", []):
        if feature.get("geometry") is None:
            continue

        geometry_type = feature["geometry"]["type"]
        properties = feature.get("properties", {})

        # Extract element type and id from @id or id field
        elem_id_str = properties.get("@id", feature.get("id", ""))
        if "/" in elem_id_str:
            elem_type_str, elem_id_part = elem_id_str.split("/", 1)
            elem_id = int(elem_id_part)
        else:
            elem_type_str = None
            elem_id = None

        if geometry_type == "Point":
            # Create a node
            coords = feature["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]

            node: dict[str, Any] = {"type": "node", "id": elem_id if elem_id else node_id_counter, "lat": lat, "lon": lon}

            # Add metadata (remove @ prefix)
            metadata_keys = ["timestamp", "version", "changeset", "user", "uid"]
            for key in metadata_keys:
                at_key = f"@{key}"
                if at_key in properties:
                    node[key] = properties[at_key]

            # Add tags (exclude @ prefixed properties and @id)
            tags = {k: v for k, v in properties.items() if not k.startswith("@")}
            if tags:
                node["tags"] = tags

            elements.append(node)  # type: ignore[arg-type]
            node_map[(lon, lat)] = node["id"]

            if not elem_id:
                node_id_counter += 1

    # Second pass: create ways from LineString and Polygon geometries
    for feature in geojson_data.get("features", []):
        if feature.get("geometry") is None:
            continue

        geometry_type = feature["geometry"]["type"]
        properties = feature.get("properties", {})

        # Extract element type and id
        elem_id_str = properties.get("@id", feature.get("id", ""))
        if "/" in elem_id_str:
            elem_type_str, elem_id_part = elem_id_str.split("/", 1)
            elem_id = int(elem_id_part)
        else:
            elem_type_str = "way"
            elem_id = node_id_counter
            node_id_counter += 1

        if geometry_type in ["LineString", "Polygon"]:
            # Create a way
            way: dict[str, Any] = {"type": "way", "id": elem_id}

            # Get coordinates
            if geometry_type == "LineString":
                coords_list = feature["geometry"]["coordinates"]
            else:  # Polygon
                coords_list = feature["geometry"]["coordinates"][0]  # Outer ring

            # Create or reference nodes
            node_refs: list[int] = []
            for coord in coords_list:
                lon, lat = coord[0], coord[1]
                coord_key = (lon, lat)

                # Check if node already exists
                if coord_key in node_map:
                    node_refs.append(node_map[coord_key])
                else:
                    # Create a new node
                    new_node_id = node_id_counter
                    node_id_counter += 1
                    new_node: dict[str, Any] = {"type": "node", "id": new_node_id, "lat": lat, "lon": lon}
                    elements.append(new_node)  # type: ignore[arg-type]
                    node_map[coord_key] = new_node_id
                    node_refs.append(new_node_id)

            way["nodes"] = node_refs

            # Add metadata
            metadata_keys = ["timestamp", "version", "changeset", "user", "uid"]
            for key in metadata_keys:
                at_key = f"@{key}"
                if at_key in properties:
                    way[key] = properties[at_key]

            # Add tags
            tags = {k: v for k, v in properties.items() if not k.startswith("@")}
            if tags:
                way["tags"] = tags

            elements.append(way)  # type: ignore[arg-type]

    # Build OSM JSON structure
    result: OSMData = {  # type: ignore[typeddict-item]
        "version": "0.6",
        "generator": geojson_data.get("generator", "osm_converter"),
        "elements": elements,
    }

    # Add copyright if present
    if "copyright" in geojson_data:
        result["copyright"] = geojson_data["copyright"]  # type: ignore[typeddict-item]

    return result


def convert_json_to_geojson_file(json_path: Path, geojson_path: Path) -> None:
    """Convert OSM JSON file to GeoJSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    geojson_data = osm_json_to_geojson(json_data)
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2, ensure_ascii=False)


def convert_geojson_to_json_file(geojson_path: Path, json_path: Path) -> None:
    """Convert GeoJSON file to OSM JSON file."""
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)
    json_data = geojson_to_osm_json(geojson_data)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)


def convert_xml_to_geojson_file(xml_path: Path, geojson_path: Path) -> None:
    """Convert OSM XML file to GeoJSON file."""
    json_data = osm_xml_to_json(xml_path)
    geojson_data = osm_json_to_geojson(json_data)
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2, ensure_ascii=False)


def convert_geojson_to_xml_file(geojson_path: Path, xml_path: Path) -> None:
    """Convert GeoJSON file to OSM XML file."""
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)
    json_data = geojson_to_osm_json(geojson_data)
    root = osm_json_to_xml_from_data(json_data)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True)


def osm_json_to_csv(json_data: OSMData, csv_path: Path) -> None:
    """
    Convert OSM JSON data to CSV format.

    Only nodes and ways with at least one "name" or "name:*" tag are included.
    Relations are always ignored. Each tag key becomes a column.

    Args:
        json_data: Dictionary representing the OSM JSON structure
        csv_path: Path to the output CSV file
    """
    # First pass: collect all unique tag keys
    all_keys: set[str] = set()
    elements: list[OSMElement] = []

    for element in json_data.get("elements", []):
        elem_type = element.get("type")

        # Skip relations
        if elem_type == "relation":
            continue

        # Only process nodes and ways
        if elem_type in ("node", "way"):
            tags = element.get("tags", {})

            # Check if element has at least one name or name:* tag
            has_name = any(key == "name" or key.startswith("name:") for key in tags.keys())

            # Skip elements without name tags
            if not has_name:
                continue

            elements.append(element)

            # Collect tag keys
            all_keys.update(tags.keys())

    # Separate name tags from other tags
    # Only include name keys matching: "name", "name:en\d?", "name:he\d?", "name:ar\d?"
    # Pattern: exact "name" OR "name:(en|he|ar)" followed by optional single digit
    name_pattern = re.compile(r'^name:(en|he|ar)\d?$')
    name_keys: list[str] = []
    other_keys: list[str] = []

    for key in all_keys:
        if key == "name":
            name_keys.append(key)
        elif name_pattern.match(key):
            name_keys.append(key)
        elif key.startswith("name:"):
            # Skip other name:* tags that don't match the criteria
            continue
        else:
            other_keys.append(key)

    # Sort name tags (with "name" first if it exists, then "name:*" alphabetically)
    name_keys.sort()
    if "name" in name_keys:
        # Move "name" to the front
        name_keys.remove("name")
        name_keys.insert(0, "name")

    # Sort other tags alphabetically
    other_keys.sort()

    # Combine: name tags first, then other tags
    sorted_keys = name_keys + other_keys

    # Define CSV columns: id, type, then all tag keys
    columns = ["id", "type"] + sorted_keys

    # Write CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        for element in elements:
            row: dict[str, str] = {
                "id": str(element.get("id", "")),
                "type": str(element.get("type", "")),
            }

            # Add tag values
            tags = element.get("tags", {})
            for key in sorted_keys:
                row[key] = tags.get(key, "")

            writer.writerow(row)


def convert_json_to_csv_file(json_path: Path, csv_path: Path) -> None:
    """Convert OSM JSON file to CSV file."""
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    osm_json_to_csv(json_data, csv_path)


def convert_xml_to_csv_file(xml_path: Path, csv_path: Path) -> None:
    """Convert OSM XML file to CSV file."""
    json_data = osm_xml_to_json(xml_path)
    osm_json_to_csv(json_data, csv_path)


def main() -> None:
    """Main entry point for CLI usage."""
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  XML to JSON: osm_converter.py <input.osm> <output.json>")
        print("  JSON to XML: osm_converter.py <input.json> <output.osm>")
        print("  XML to L0L:  osm_converter.py <input.osm> <output.l0l>")
        print("  L0L to XML:  osm_converter.py <input.l0l> <output.osm>")
        print("  JSON to L0L: osm_converter.py <input.json> <output.l0l>")
        print("  L0L to JSON: osm_converter.py <input.l0l> <output.json>")
        print("  XML to OsmChange: osm_converter.py <input.osm> <output.osc>")
        print("  JSON to OsmChange: osm_converter.py <input.json> <output.osc>")
        print("  XML to GeoJSON: osm_converter.py <input.osm> <output.geojson>")
        print("  JSON to GeoJSON: osm_converter.py <input.json> <output.geojson>")
        print("  GeoJSON to XML: osm_converter.py <input.geojson> <output.osm>")
        print("  GeoJSON to JSON: osm_converter.py <input.geojson> <output.json>")
        print("  XML to CSV: osm_converter.py <input.osm> <output.csv>")
        print("  JSON to CSV: osm_converter.py <input.json> <output.csv>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist")
        sys.exit(1)

    # Determine conversion direction based on file extensions
    in_ext = input_path.suffix
    out_ext = output_path.suffix

    if in_ext == ".osm" and out_ext == ".json":
        print(f"Converting {input_path} (XML) -> {output_path} (JSON)")
        convert_xml_to_json_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".json" and out_ext == ".osm":
        print(f"Converting {input_path} (JSON) -> {output_path} (XML)")
        convert_json_to_xml_file(json_path=input_path, xml_path=output_path)
        print("Conversion complete!")
    elif in_ext == ".osm" and out_ext == ".l0l":
        print(f"Converting {input_path} (XML) -> {output_path} (L0L)")
        convert_xml_to_l0l_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".l0l" and out_ext == ".osm":
        print(f"Converting {input_path} (L0L) -> {output_path} (XML)")
        convert_l0l_to_xml_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".json" and out_ext == ".l0l":
        print(f"Converting {input_path} (JSON) -> {output_path} (L0L)")
        convert_json_to_l0l_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".l0l" and out_ext == ".json":
        print(f"Converting {input_path} (L0L) -> {output_path} (JSON)")
        convert_l0l_to_json_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".osm" and out_ext == ".osc":
        print(f"Converting {input_path} (JOSM XML) -> {output_path} (OsmChange)")
        try:
            convert_xml_to_osmchange_file(input_path, output_path)
            print("Conversion complete!")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif in_ext == ".json" and out_ext == ".osc":
        print(f"Converting {input_path} (JOSM JSON) -> {output_path} (OsmChange)")
        try:
            convert_json_to_osmchange_file(input_path, output_path)
            print("Conversion complete!")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif in_ext == ".osm" and out_ext == ".geojson":
        print(f"Converting {input_path} (OSM XML) -> {output_path} (GeoJSON)")
        convert_xml_to_geojson_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".json" and out_ext == ".geojson":
        print(f"Converting {input_path} (OSM JSON) -> {output_path} (GeoJSON)")
        convert_json_to_geojson_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".geojson" and out_ext == ".osm":
        print(f"Converting {input_path} (GeoJSON) -> {output_path} (OSM XML)")
        convert_geojson_to_xml_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".geojson" and out_ext == ".json":
        print(f"Converting {input_path} (GeoJSON) -> {output_path} (OSM JSON)")
        convert_geojson_to_json_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".osm" and out_ext == ".csv":
        print(f"Converting {input_path} (OSM XML) -> {output_path} (CSV)")
        convert_xml_to_csv_file(input_path, output_path)
        print("Conversion complete!")
    elif in_ext == ".json" and out_ext == ".csv":
        print(f"Converting {input_path} (OSM JSON) -> {output_path} (CSV)")
        convert_json_to_csv_file(input_path, output_path)
        print("Conversion complete!")
    else:
        print(
            f"Error: Invalid file extension combination ({in_ext} -> {out_ext}). "
            "Use .osm for XML, .json for JSON, .l0l for Level0L, .osc for OsmChange, .geojson for GeoJSON, and .csv for CSV"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
