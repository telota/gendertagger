#!/usr/bin/env python3
"""
Extract institution entries from the Personen register (A-Z.xml),
transform <person> → <org> elements, and write them to a new
Institutionen.xml file with a <listOrg> wrapper.

Source files are NOT modified (read-only extraction).
Use --clean to remove institution entries from source files.

Transformation mapping:
  <person @xml:id>  →  <org @xml:id>
  <persName type="reg"><surname>…</surname><forename>…</forename></persName>
      →  <orgName type="reg">surname, forename</orgName>  (plain text)
  <persName type="alt">  →  <orgName type="alt">
  <note>  →  <desc>  (preserve mixed content: <persName>, <placeName>, etc.)
  <idno>  →  <idno>  (keep as-is)
  <birth>, <death>, <sex>  →  DROP

Group handling in output:
  - Pure-institution groups → <listOrg><head>…</head><org>…</org>…</listOrg>
  - Mixed groups → institution members extracted as standalone <org>
  - Top-level institutions → standalone <org>
"""

import csv
import copy
import re
import sys
from pathlib import Path
from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"
XML = "{http://www.w3.org/XML/1998/namespace}"

REGISTER_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "raw"
    / "schleiermacher"
    / "Register"
)
PERSONEN_DIR = REGISTER_DIR / "Personen"
CSV_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "output" / "gender_reviewed.csv"
)
OUTPUT_PATH = REGISTER_DIR / "Institutionen.xml"

# Elements to drop during transformation
DROP_ELEMENTS = {"birth", "death", "sex"}
# Elements to rename
RENAME_MAP = {"persName": "orgName", "note": "desc"}


def load_institution_ids(csv_path: Path) -> set[str]:
    """Load xml_ids of all entries classified as 'institution'."""
    ids = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gender = (
                row.get("corrected_gender", "").strip()
                or row.get("predicted_gender", "").strip()
            )
            if gender == "institution":
                ids.add(row["xml_id"])
    return ids


def _collect_pis(elem: etree._Element) -> list[etree._ProcessingInstruction]:
    """Collect all processing instructions that are direct children of elem."""
    return [child for child in elem if isinstance(child, etree._ProcessingInstruction)]


def transform_person_to_org(person_elem: etree._Element) -> etree._Element:
    """Transform a <person> element into an <org> element."""
    org = etree.Element(f"{TEI}org")
    org.set(f"{XML}id", person_elem.get(f"{XML}id"))

    for child in person_elem:
        # Preserve processing instructions (oxy_comment_start/end etc.)
        if isinstance(child, etree._ProcessingInstruction):
            org.append(copy.deepcopy(child))
            continue

        # Skip other non-element nodes (comments)
        if not isinstance(child.tag, str):
            continue

        tag_local = etree.QName(child).localname

        # Drop birth, death, sex
        if tag_local in DROP_ELEMENTS:
            continue

        if tag_local == "idno":
            org.append(copy.deepcopy(child))

        elif tag_local == "persName":
            ptype = child.get("type", "")
            # Collect PIs from inside persName to attach after the orgName
            pis_inside = _collect_pis(child)

            if ptype == "reg":
                # Build plain-text orgName from surname + forename
                surname_el = child.find(f"{TEI}surname")
                forename_el = child.find(f"{TEI}forename")
                surname = (
                    (surname_el.text or "").strip() if surname_el is not None else ""
                )
                forename = (
                    (forename_el.text or "").strip() if forename_el is not None else ""
                )
                name_text = f"{surname}, {forename}" if forename else surname

                org_name = etree.SubElement(org, f"{TEI}orgName")
                org_name.set("type", "reg")
                org_name.text = name_text

            elif ptype == "alt":
                # Copy alt name as <orgName type="alt"> with text content
                alt_name = etree.SubElement(org, f"{TEI}orgName")
                alt_name.set("type", "alt")
                # Alt names may have <name>, surname/forename, or plain text
                name_el = child.find(f"{TEI}name")
                surname_el = child.find(f"{TEI}surname")
                forename_el = child.find(f"{TEI}forename")
                if name_el is not None:
                    alt_name.text = (name_el.text or "").strip()
                elif surname_el is not None:
                    surname = (surname_el.text or "").strip()
                    forename = (
                        (forename_el.text or "").strip()
                        if forename_el is not None
                        else ""
                    )
                    alt_name.text = f"{surname}, {forename}" if forename else surname
                else:
                    alt_name.text = (child.text or "").strip()
            else:
                # Other persName types — convert to orgName preserving type
                org_name = etree.SubElement(org, f"{TEI}orgName")
                if ptype:
                    org_name.set("type", ptype)
                org_name.text = child.text

            # Append any PIs that were inside the persName
            for pi in pis_inside:
                org.append(copy.deepcopy(pi))

        elif tag_local == "note":
            # Transform <note> → <desc>, preserving mixed content (incl. PIs)
            desc = copy.deepcopy(child)
            desc.tag = f"{TEI}desc"
            org.append(desc)

        elif tag_local == "linkGrp":
            org.append(copy.deepcopy(child))

        # Anything else is silently dropped (shouldn't occur based on analysis)

    return org


def build_output_xml(items: list) -> str:
    """Build the Institutionen.xml output as a formatted string.

    items is a list of either:
      - etree._Element (<org>)  — standalone org
      - tuple (head_text, [<org>, ...])  — org group
    """

    def _serialize(elem):
        raw = etree.tostring(elem, encoding="unicode")
        # Remove namespace declarations and prefixes that lxml adds
        raw = raw.replace(' xmlns:ns0="http://www.tei-c.org/ns/1.0"', "")
        raw = raw.replace(' xmlns="http://www.tei-c.org/ns/1.0"', "")
        raw = raw.replace(' xmlns:telota="http://www.telota.de"', "")
        raw = raw.replace(' xmlns:xs="http://www.w3.org/2001/XMLSchema"', "")
        raw = raw.replace("ns0:", "").replace("</ns0:", "</")
        return raw

    lines = []
    lines.append(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:telota="http://www.telota.de" xmlns:xs="http://www.w3.org/2001/XMLSchema" telota:doctype="register" xml:id="TODO">'
    )
    lines.append("   <teiHeader>")
    lines.append("      <fileDesc>")
    lines.append("         <titleStmt>")
    lines.append("            <title>Institutionenregister</title>")
    lines.append("         </titleStmt>")
    lines.append("         <publicationStmt>")
    lines.append("            <p>Publication Information</p>")
    lines.append("         </publicationStmt>")
    lines.append("         <sourceDesc>")
    lines.append("            <p>Information about the source</p>")
    lines.append("         </sourceDesc>")
    lines.append("      </fileDesc>")
    lines.append("   </teiHeader>")
    lines.append("   <text>")
    lines.append("      <body>")
    lines.append("         <listOrg>")

    for item in items:
        if isinstance(item, tuple):
            head_text, group_orgs = item
            lines.append("            <listOrg>")
            lines.append(f"               <head>{head_text}</head>")
            for org in group_orgs:
                raw = _serialize(org)
                indented = re.sub(r"^", "               ", raw, flags=re.MULTILINE)
                lines.append(indented)
            lines.append("            </listOrg>")
        else:
            raw = _serialize(item)
            indented = re.sub(r"^", "            ", raw, flags=re.MULTILINE)
            lines.append(indented)

    lines.append("         </listOrg>")
    lines.append("      </body>")
    lines.append("   </text>")
    lines.append("</TEI>")
    return "\n".join(lines) + "\n"


def process_files(inst_ids: set[str]):
    """
    Process all A-Z.xml files (read-only).
    Extract institution <person> elements, transform to <org>,
    and preserve group structure for pure-institution groups.

    Returns a list of items (standalone <org> or (head, [<org>...]) tuples),
    plus stats dict.
    """
    items = []  # standalone orgs or (head_text, [orgs]) tuples
    stats = {
        "extracted": 0,
        "pure_groups": 0,
        "mixed_group_members": 0,
        "standalone": 0,
    }
    # Track which persons have already been handled via groups
    handled_ids = set()

    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        xml_path = PERSONEN_DIR / f"{letter}.xml"
        if not xml_path.exists():
            continue

        parser = etree.XMLParser(remove_comments=False, remove_pis=False)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()

        # First pass: handle groups
        for lp in root.iter(f"{TEI}listPerson"):
            if lp.get("type") != "group":
                continue
            members = lp.findall(f"{TEI}person")
            inst_members = [m for m in members if m.get(f"{XML}id") in inst_ids]
            non_inst = [m for m in members if m.get(f"{XML}id") not in inst_ids]

            if not inst_members:
                continue

            if len(non_inst) == 0:
                # Pure institution group → listOrg with head
                head_el = lp.find(f"{TEI}head")
                head_text = head_el.text if head_el is not None else ""
                group_orgs = []
                for m in inst_members:
                    org = transform_person_to_org(m)
                    group_orgs.append(org)
                    handled_ids.add(m.get(f"{XML}id"))
                    stats["extracted"] += 1
                items.append((head_text, group_orgs))
                stats["pure_groups"] += 1
            else:
                # Mixed group → extract institution members as standalone
                for m in inst_members:
                    org = transform_person_to_org(m)
                    items.append(org)
                    handled_ids.add(m.get(f"{XML}id"))
                    stats["extracted"] += 1
                    stats["mixed_group_members"] += 1

        # Second pass: top-level persons (not in groups or not yet handled)
        for person in root.iter(f"{TEI}person"):
            xid = person.get(f"{XML}id")
            if xid not in inst_ids or xid in handled_ids:
                continue
            org = transform_person_to_org(person)
            items.append(org)
            stats["extracted"] += 1
            stats["standalone"] += 1

    return items, stats


def clean_source_files(inst_ids: set[str], dry_run: bool = False):
    """Remove institution entries from source A-Z.xml files."""
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        xml_path = PERSONEN_DIR / f"{letter}.xml"
        if not xml_path.exists():
            continue

        parser = etree.XMLParser(remove_comments=False, remove_pis=False)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()

        elements_to_remove = []

        for person in root.iter(f"{TEI}person"):
            xid = person.get(f"{XML}id")
            if xid not in inst_ids:
                continue

            parent = person.getparent()
            if (
                parent is not None
                and parent.tag == f"{TEI}listPerson"
                and parent.get("type") == "group"
            ):
                siblings = parent.findall(f"{TEI}person")
                non_inst = [s for s in siblings if s.get(f"{XML}id") not in inst_ids]
                if len(non_inst) == 0:
                    if parent not in elements_to_remove:
                        elements_to_remove.append(parent)
                else:
                    elements_to_remove.append(person)
            else:
                elements_to_remove.append(person)

        if elements_to_remove:
            if dry_run:
                print(
                    f"  {letter}.xml: would remove {len(elements_to_remove)} element(s)"
                )
            else:
                for elem in elements_to_remove:
                    parent = elem.getparent()
                    if parent is not None:
                        prev = elem.getprevious()
                        if prev is not None and elem.tail:
                            prev.tail = (prev.tail or "") + elem.tail
                        parent.remove(elem)
                output = etree.tostring(tree, encoding="unicode", xml_declaration=False)
                xml_path.write_text(output, encoding="utf-8")
                print(f"  {letter}.xml: removed {len(elements_to_remove)} element(s)")


def main():
    dry_run = "--dry-run" in sys.argv
    clean = "--clean" in sys.argv

    mode = "CLEAN (dry)" if clean and dry_run else "CLEAN" if clean else "EXTRACT ONLY"
    print(f"Mode: {mode}")
    print(f"CSV: {CSV_PATH}")
    print(f"Register: {PERSONEN_DIR}")
    print(f"Output: {OUTPUT_PATH}")
    print()

    # Load institution IDs
    inst_ids = load_institution_ids(CSV_PATH)
    print(f"Institution IDs from CSV: {len(inst_ids)}")

    # Extract and write output
    if not OUTPUT_PATH.exists():
        items, stats = process_files(inst_ids)

        print()
        print(f"Extracted: {stats['extracted']} institution entries")
        print(f"  Standalone: {stats['standalone']}")
        print(f"  Pure-institution groups: {stats['pure_groups']}")
        print(f"  Members from mixed groups: {stats['mixed_group_members']}")

        if items:
            output_xml = build_output_xml(items)
            OUTPUT_PATH.write_text(output_xml, encoding="utf-8")
            print(f"\nWrote {OUTPUT_PATH}")
    else:
        print(f"\n{OUTPUT_PATH} already exists, skipping extraction.")

    # Optionally clean source files
    if clean:
        print("\nCleaning source files...")
        clean_source_files(inst_ids, dry_run=dry_run)


if __name__ == "__main__":
    main()
