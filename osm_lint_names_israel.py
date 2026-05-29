#!/usr/bin/env python3
import copy
import re
import sys
import xml.etree.ElementTree as ET

HEBREW_RE = re.compile(r"[֐-׿יִ-ﭏ]")
ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def error(ref: str, text: str, fixed: bool) -> None:
    suffix = " [fix]" if fixed else " [no fix]"
    print(f"{ref}: {text}{suffix}")


def is_hebrew(text: str) -> bool:
    return bool(HEBREW_RE.search(text))


def is_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text))


def lint_element(elem: ET.Element) -> dict[str, str]:
    """Lint element and return dict of tag changes to apply. Empty if skipped or no changes."""
    if elem.get("action") is not None:
        return {}

    ref = f"{elem.tag}/{elem.get('id', '?')}"
    tags: dict[str, str] = {t.get("k"): t.get("v") for t in elem.findall("tag")}
    name = tags.get("name")
    lang_tags: dict[str, str] = {k: v for k, v in tags.items() if re.match(r"^name:.+$", k)}

    changes: dict[str, str] = {}

    # name:* exists but name does not
    if lang_tags and name is None:
        keys = ", ".join(sorted(lang_tags.keys()))
        fix: dict[str, str] = {}
        if "name:he" in lang_tags:
            fix["name"] = lang_tags["name:he"]
        elif "name:en" in lang_tags:
            fix["name"] = lang_tags["name:en"]
        changes.update(fix)
        error(ref, f"has {keys} but no 'name' tag", bool(fix))

    if name is not None:
        # name value not found in any name:* tag
        if lang_tags and name not in lang_tags.values() and not is_arabic(name):
            fix = {}
            if is_hebrew(name) and "name:he" not in tags:
                fix["name:he"] = name
            elif not is_hebrew(name) and "name:en" not in tags:
                fix["name:en"] = name
            changes.update(fix)
            error(ref, f"name \"{name}\" not duplicated in any name:* tag", bool(fix))

        # name is Hebrew but name:he missing
        if is_hebrew(name) and "name:he" not in tags:
            changes["name:he"] = name
            error(ref, f"name \"{name}\" is Hebrew but 'name:he' is missing", True)

    return changes


def _patch_elem(elem: ET.Element, changes: dict[str, str]) -> None:
    elem.set("action", "modify")
    existing = {t.get("k"): t for t in elem.findall("tag")}
    for k, v in changes.items():
        if k in existing:
            existing[k].set("v", v)
        else:
            ET.SubElement(elem, "tag", {"k": k, "v": v})


def lint_file(path: str, changefile: str | None, only_changes: bool = False) -> None:
    tree = ET.parse(path)
    root = tree.getroot()

    modifications: list[tuple[ET.Element, dict[str, str]]] = []

    for elem in root.iter():
        if elem.tag in ("node", "way", "relation"):
            changes = lint_element(elem)
            if changes:
                modifications.append((elem, changes))

    if changefile:
        write_changefile(tree, modifications, changefile, only_changes)


def write_changefile(src: ET.ElementTree, modifications: list[tuple[ET.Element, dict[str, str]]], path: str, only_changes: bool) -> None:
    mod_map: dict[tuple[str, str], dict[str, str]] = {
        (elem.tag, elem.get("id", "")): changes
        for elem, changes in modifications
    }

    if only_changes:
        src_root = src.getroot()
        new_root = ET.Element(src_root.tag, src_root.attrib)
        for child in src_root:
            if child.tag not in ("node", "way", "relation"):
                new_root.append(copy.deepcopy(child))
            else:
                changes = mod_map.get((child.tag, child.get("id", "")))
                if changes is None:
                    continue
                new_child = copy.deepcopy(child)
                _patch_elem(new_child, changes)
                new_root.append(new_child)
        out = ET.ElementTree(new_root)
    else:
        out = copy.deepcopy(src)
        for elem in out.getroot().iter():
            if elem.tag not in ("node", "way", "relation"):
                continue
            changes = mod_map.get((elem.tag, elem.get("id", "")))
            if changes is None:
                continue
            _patch_elem(elem, changes)

    ET.indent(out, space="  ")
    out.write(path, encoding="unicode", xml_declaration=True)


def main() -> None:
    args = sys.argv[1:]
    only_changes = "--only-changes" in args
    args = [a for a in args if a != "--only-changes"]

    if len(args) < 1:
        print(f"Usage: {sys.argv[0]} [--only-changes] <file.osm> [changefile.osm]", file=sys.stderr)
        sys.exit(1)

    changefile = args[1] if len(args) >= 2 else None
    lint_file(args[0], changefile, only_changes)


if __name__ == "__main__":
    main()
