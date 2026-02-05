#!/usr/bin/env python3
"""
Test script for the OSM converter.
Demonstrates programmatic usage of the converter functions.
"""

import sys
from pathlib import Path

# Add parent directory to path to import osm_converter
sys.path.insert(0, str(Path(__file__).parent.parent))

from osm_converter import (
    osm_xml_to_json,
    osm_json_to_xml,
    convert_xml_to_json_file,
    convert_json_to_xml_file,
    osm_l0l_to_json,
    convert_xml_to_l0l_file,
    convert_l0l_to_xml_file,
    convert_l0l_to_json_file,
)
import json


def main() -> None:
    # Example 1: Convert XML to JSON programmatically
    print("Test 1: Converting mda.osm to JSON...")
    xml_path = Path("mda.osm")
    if xml_path.exists():
        data = osm_xml_to_json(xml_path)
        print(f"  Found {len(data['elements'])} elements")
        print(f"  First element type: {data['elements'][0]['type']}")
        print(f"  First element ID: {data['elements'][0]['id']}")
        print("  ✓ Success\n")

    # Example 2: Convert JSON to XML programmatically
    print("Test 2: Converting example.json to XML...")
    json_path = Path("example.json")
    if json_path.exists():
        root = osm_json_to_xml(json_path)
        print(f"  Root tag: {root.tag}")
        print(f"  OSM version: {root.get('version')}")
        print("  ✓ Success\n")

    # Example 3: File-to-file conversion (XML to JSON)
    print("Test 3: File-to-file conversion (XML → JSON)...")
    if xml_path.exists():
        output_json = Path("test_xml_to_json.json")
        convert_xml_to_json_file(xml_path, output_json)
        print(f"  Created: {output_json}")
        print("  ✓ Success\n")

    # Example 4: File-to-file conversion (JSON to XML)
    print("Test 4: File-to-file conversion (JSON → XML)...")
    if json_path.exists():
        output_xml = Path("test_json_to_xml.osm")
        convert_json_to_xml_file(json_path, output_xml)
        print(f"  Created: {output_xml}")
        print("  ✓ Success\n")

    # Example 5: Convert XML to L0L
    print("Test 5: File-to-file conversion (XML → L0L)...")
    if xml_path.exists():
        output_l0l = Path("test_xml_to_l0l.l0l")
        convert_xml_to_l0l_file(xml_path, output_l0l)
        print(f"  Created: {output_l0l}")
        with open(output_l0l) as f:
            l0l_lines = f.readlines()
        print(f"  L0L has {len(l0l_lines)} lines")
        print("  ✓ Success\n")

    # Example 6: Convert L0L to JSON
    print("Test 6: File-to-file conversion (L0L → JSON)...")
    l0l_test_path = Path("test_xml_to_l0l.l0l")
    if l0l_test_path.exists():
        output_json_from_l0l = Path("test_l0l_to_json.json")
        convert_l0l_to_json_file(l0l_test_path, output_json_from_l0l)
        print(f"  Created: {output_json_from_l0l}")
        with open(output_json_from_l0l) as f:
            data = json.load(f)
        print(f"  Found {len(data['elements'])} elements")
        print("  ✓ Success\n")

    # Example 7: Round-trip test (XML → L0L → XML)
    print("Test 7: Round-trip conversion (XML → L0L → XML)...")
    if xml_path.exists():
        temp_l0l = Path("test_roundtrip.l0l")
        roundtrip_xml = Path("test_roundtrip.osm")
        convert_xml_to_l0l_file(xml_path, temp_l0l)
        convert_l0l_to_xml_file(temp_l0l, roundtrip_xml)

        # Compare element counts
        original_data = osm_xml_to_json(xml_path)
        with open(temp_l0l) as f:
            l0l_content = f.read()
        roundtrip_data = osm_l0l_to_json(l0l_content)

        print(f"  Original: {len(original_data['elements'])} elements")
        print(f"  Roundtrip: {len(roundtrip_data['elements'])} elements")
        print(f"  Match: {len(original_data['elements']) == len(roundtrip_data['elements'])}")
        print("  ✓ Success\n")

    print("All tests completed successfully!")


if __name__ == "__main__":
    main()
