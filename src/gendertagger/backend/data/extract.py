# Script to create parquet file with letters from xml data

"""
TEI-XML data extraction utilities for person registers.
"""
from pathlib import Path
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
import pandas as pd


# TEI namespace
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def parse_tei_person_register(xml_path: Path) -> List[Dict]:
    """
    Parse a TEI-XML person register file.

    Args:
        xml_path: Path to the TEI-XML file

    Returns:
        List of person dictionaries
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    persons = []

    # Find all person elements
    for person_elem in root.findall(".//tei:person", TEI_NS):
        person_id = person_elem.get("{http://www.w3.org/XML/1998/namespace}id", "")
        sex = person_elem.get("sex", "")

        # Extract name components
        persName = person_elem.find(".//tei:persName", TEI_NS)
        forename = ""
        surname = ""
        name = ""

        if persName is not None:
            forename_elem = persName.find(".//tei:forename", TEI_NS)
            surname_elem = persName.find(".//tei:surname", TEI_NS)
            name_elem = persName.find(".//tei:name", TEI_NS)

            if forename_elem is not None and forename_elem.text:
                forename = forename_elem.text.strip()
            if surname_elem is not None and surname_elem.text:
                surname = surname_elem.text.strip()

            # Build full name from components
            if surname and forename:
                name = f"{forename} {surname}".strip()
            elif surname:
                name = surname
            elif forename:
                name = forename
            elif name_elem is not None and name_elem.text:
                # Use <name> tag if present (e.g., <persName><name>Appian</name></persName>)
                name = name_elem.text.strip()

        # Extract birth and death dates
        birth_elem = person_elem.find(".//tei:birth", TEI_NS)
        death_elem = person_elem.find(".//tei:death", TEI_NS)

        birth_date = ""
        death_date = ""

        if birth_elem is not None:
            birth_date = birth_elem.get("when", "") or (birth_elem.text or "").strip()

        if death_elem is not None:
            death_date = death_elem.get("when", "") or (death_elem.text or "").strip()

        # Extract notes
        notes = []
        for note in person_elem.findall(".//tei:note", TEI_NS):
            if note.text:
                notes.append(note.text.strip())
        notes_text = " | ".join(notes) if notes else ""

        # Extract GND identifier
        gnd_id = ""
        for idno in person_elem.findall(".//tei:idno", TEI_NS):
            idno_type = idno.get("type", "")
            if idno_type == "gnd" and idno.text:
                gnd_id = idno.text.strip()
                break

        # Create person dict
        person = {
            "xml_id": person_id,
            "name": name,
            "forename": forename,
            "surname": surname,
            "sex": sex,
            "birth_date": birth_date,
            "death_date": death_date,
            "notes": notes_text,
            "gnd_id": gnd_id,
            "source_file": str(xml_path.name),
        }

        persons.append(person)

    return persons


def load_multiple_tei_files(xml_paths: List[Path]) -> pd.DataFrame:
    """
    Load multiple TEI-XML files and combine into a single DataFrame.

    Args:
        xml_paths: List of paths to TEI-XML files

    Returns:
        DataFrame with all persons
    """
    all_persons = []

    for xml_path in xml_paths:
        try:
            persons = parse_tei_person_register(xml_path)
            all_persons.extend(persons)
        except Exception as e:
            print(f"Error parsing {xml_path}: {e}")

    return pd.DataFrame(all_persons)


def load_person_register_from_directory(
    directory: Path, pattern: str = "*.xml"
) -> pd.DataFrame:
    """
    Load all person register files from a directory.

    Args:
        directory: Path to directory containing XML files
        pattern: Glob pattern to match files (default: "*.xml")

    Returns:
        DataFrame with all persons
    """
    xml_files = list(directory.glob(pattern))

    # Filter out non-XML files like .txt
    xml_files = [f for f in xml_files if f.suffix.lower() == ".xml"]

    if not xml_files:
        print(f"No XML files matching '{pattern}' found in {directory}")
        return pd.DataFrame()

    print(f"Found {len(xml_files)} XML files")
    return load_multiple_tei_files(xml_files)


def export_enriched_tei(
    original_xml_path: Path, output_path: Path, gender_annotations: Dict[str, str]
) -> None:
    """
    Export TEI-XML with added gender annotations.

    Args:
        original_xml_path: Path to original TEI-XML file
        output_path: Path where enriched file should be saved
        gender_annotations: Dictionary mapping person xml_id to gender value
    """
    # Parse original
    tree = ET.parse(original_xml_path)
    root = tree.getroot()

    # Update person elements
    for person_elem in root.findall(".//tei:person", TEI_NS):
        person_id = person_elem.get("{http://www.w3.org/XML/1998/namespace}id", "")

        if person_id in gender_annotations:
            gender = gender_annotations[person_id]

            # Map to TEI @sex values
            sex_value = ""
            if gender == "male":
                sex_value = "M"
            elif gender == "female":
                sex_value = "F"
            elif gender == "institution":
                sex_value = "O"  # Other/Organization

            if sex_value:
                person_elem.set("sex", sex_value)

    # Write out
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Exported enriched TEI to {output_path}")
