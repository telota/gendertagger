"""
Extract persons from Schleiermacher TEI-XML person register files
and write data/input/schleiermacher_persons.csv.

Columns:
    xml_id      – person xml:id
    gnd_uri     – GND URI from <idno type="uri">
    surname     – from <persName type="reg"><surname>
    forename    – from <persName type="reg"><forename> (text only, strips inner tags)
    birth       – text content of <birth>
    death       – text content of <death>
    note        – full text content of <note> (including inner elements)
    alt_names   – JSON array of {subtype, name} from <persName type="alt"> entries
                  (empty string when none)

Usage (run from project root):
    python scripts/create_input_csv.py
"""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REGISTER_DIR = Path("data/raw/schleiermacher/Register/Personen")
OUTPUT_CSV = Path("data/input/schleiermacher_persons.csv")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _all_text(elem) -> str:
    """Return all text content of an element including text in child elements."""
    return "".join(elem.itertext()).strip()


def parse_file(xml_path: Path) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    persons = []

    for person in root.findall(".//tei:person", TEI_NS):
        xml_id = person.get(XML_ID, "")
        if not xml_id:
            continue

        # GND URI
        gnd_uri = ""
        for idno in person.findall("tei:idno", TEI_NS):
            if idno.get("type") == "uri" and idno.text:
                gnd_uri = idno.text.strip()
                break

        # Primary name (type="reg")
        # Handles two TEI patterns:
        #   standard persons:  <surname> + <forename>
        #   collectives/mononyms: bare <name> (no surname/forename child)
        surname = ""
        forename = ""
        for persName in person.findall("tei:persName", TEI_NS):
            if persName.get("type") == "reg":
                sn = persName.find("tei:surname", TEI_NS)
                fn = persName.find("tei:forename", TEI_NS)
                nm = persName.find("tei:name", TEI_NS)
                if sn is not None:
                    surname = _all_text(sn)
                if fn is not None:
                    # Use only direct text (strip inner <name type="used"> etc.)
                    forename = (fn.text or "").strip()
                # Fallback: bare <name> with no surname/forename (mononyms, collectives)
                if not surname and not forename and nm is not None:
                    surname = _all_text(nm)
                break

        # Birth / death
        birth_elem = person.find("tei:birth", TEI_NS)
        death_elem = person.find("tei:death", TEI_NS)
        birth = _all_text(birth_elem) if birth_elem is not None else ""
        death = _all_text(death_elem) if death_elem is not None else ""

        # Note (first note element, full text)
        note = ""
        note_elem = person.find("tei:note", TEI_NS)
        if note_elem is not None:
            note = _all_text(note_elem)

        # Alt names
        alt_names_list = []
        for persName in person.findall("tei:persName", TEI_NS):
            if persName.get("type") == "alt":
                name_elem = persName.find("tei:name", TEI_NS)
                name_text = (
                    _all_text(name_elem)
                    if name_elem is not None
                    else _all_text(persName)
                )
                subtype = persName.get("subtype", "")
                entry = {"name": name_text}
                if subtype:
                    entry["subtype"] = subtype
                alt_names_list.append(entry)

        alt_names = (
            json.dumps(alt_names_list, ensure_ascii=False) if alt_names_list else ""
        )

        persons.append(
            {
                "xml_id": xml_id,
                "gnd_uri": gnd_uri,
                "surname": surname,
                "forename": forename,
                "birth": birth,
                "death": death,
                "note": note,
                "alt_names": alt_names,
            }
        )

    return persons


def main():
    xml_files = sorted(REGISTER_DIR.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {REGISTER_DIR}")
        return

    print(f"Parsing {len(xml_files)} XML files from {REGISTER_DIR} ...")

    all_persons = []
    for xml_path in xml_files:
        persons = parse_file(xml_path)
        print(f"  {xml_path.name}: {len(persons)} persons")
        all_persons.extend(persons)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "xml_id",
        "gnd_uri",
        "surname",
        "forename",
        "birth",
        "death",
        "note",
        "alt_names",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_persons)

    print(f"\nDone! {len(all_persons):,} persons written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
