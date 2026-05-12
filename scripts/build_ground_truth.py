"""
Build ground truth database for genderTagger poster.

1. Parses all persons from the TEI-XML Personen register
2. Queries the lobid-gnd API for persons with GND URIs
3. Stores everything in a SQLite database

The GND gender data serves as benchmark / ground truth for classifier evaluation.

Usage:
    python src/build_ground_truth.py
"""

import sqlite3
import xml.etree.ElementTree as ET
import json
import time
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGISTER_DIR = Path("data/raw/schleiermacher/Register/Personen")
DB_PATH = Path("output/ground_truth.db")
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
GND_API_BASE = "https://lobid.org/gnd"
REQUEST_DELAY = 0.15  # seconds between API calls (be nice to the server)


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

SCHEMA = """
-- Every <person> element from the TEI-XML register
CREATE TABLE IF NOT EXISTS persons (
    xml_id          TEXT PRIMARY KEY,
    surname         TEXT,
    forename        TEXT,
    name_full       TEXT,      -- computed: "forename surname"
    birth           TEXT,
    death           TEXT,
    note            TEXT,
    role            TEXT,      -- e.g. "mythological"
    gnd_uri         TEXT,      -- https://d-nb.info/gnd/... or NULL
    gnd_id          TEXT,      -- bare GND ID (e.g. "116000988") or NULL
    source_file     TEXT,      -- which register file (A.xml, B.xml, ...)
    in_group        INTEGER DEFAULT 0  -- 1 if inside nested <listPerson type="group">
);

-- Ground truth from the GND API (only for persons with gnd_uri)
CREATE TABLE IF NOT EXISTS gnd_ground_truth (
    gnd_id              TEXT PRIMARY KEY,
    gnd_gender_id       TEXT,      -- e.g. "https://d-nb.info/standards/vocab/gnd/gender#male"
    gnd_gender_label    TEXT,      -- e.g. "Männlich", "Weiblich"
    gnd_gender_mapped   TEXT,      -- our mapping: male / female / unknown
    gnd_type            TEXT,      -- JSON array, e.g. '["DifferentiatedPerson","Person"]'
    gnd_preferred_name  TEXT,
    gnd_profession      TEXT,      -- JSON array of profession labels
    gnd_date_of_birth   TEXT,
    gnd_date_of_death   TEXT,
    http_status         INTEGER,   -- API response status
    raw_json            TEXT,      -- full API response for later re-analysis
    queried_at          TEXT,      -- ISO timestamp
    FOREIGN KEY (gnd_id) REFERENCES persons(gnd_id)
);

-- View: persons joined with GND ground truth
CREATE VIEW IF NOT EXISTS v_persons_with_ground_truth AS
SELECT
    p.*,
    g.gnd_gender_mapped,
    g.gnd_gender_label,
    g.gnd_type,
    g.gnd_preferred_name,
    g.gnd_profession
FROM persons p
LEFT JOIN gnd_ground_truth g ON p.gnd_id = g.gnd_id;
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create/open database and ensure schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Step 1: Parse TEI-XML register
# ---------------------------------------------------------------------------


def parse_person(person_elem, source_file: str, in_group: bool) -> dict:
    """Extract data from a single <person> element."""
    xml_id = person_elem.get("{http://www.w3.org/XML/1998/namespace}id", "")
    role = person_elem.get("role", "")

    # Name components
    persName = person_elem.find("tei:persName", TEI_NS)
    forename = ""
    surname = ""

    if persName is not None:
        fn_elem = persName.find("tei:forename", TEI_NS)
        sn_elem = persName.find("tei:surname", TEI_NS)
        name_elem = persName.find("tei:name", TEI_NS)

        if fn_elem is not None and fn_elem.text:
            forename = fn_elem.text.strip()
        if sn_elem is not None and sn_elem.text:
            surname = sn_elem.text.strip()
        # Fallback: <name> tag (e.g. for single-name historical figures)
        if not forename and not surname and name_elem is not None and name_elem.text:
            surname = name_elem.text.strip()

    name_full = f"{forename} {surname}".strip() if (forename or surname) else ""

    # Birth / Death
    birth_elem = person_elem.find("tei:birth", TEI_NS)
    death_elem = person_elem.find("tei:death", TEI_NS)
    birth = ""
    death = ""

    if birth_elem is not None:
        birth = (birth_elem.get("when", "") or (birth_elem.text or "")).strip()
    if death_elem is not None:
        death = (death_elem.get("when", "") or (death_elem.text or "")).strip()

    # Note (may contain nested elements, get all text)
    note_elem = person_elem.find("tei:note", TEI_NS)
    note = ""
    if note_elem is not None:
        # Get full text content including nested element tails
        note = "".join(note_elem.itertext()).strip()

    # GND URI
    gnd_uri = ""
    gnd_id = ""
    idno_elem = person_elem.find("tei:idno", TEI_NS)
    if idno_elem is not None and idno_elem.text:
        uri = idno_elem.text.strip()
        if "d-nb.info/gnd" in uri:
            gnd_uri = uri
            gnd_id = uri.rstrip("/").split("/")[-1]

    return {
        "xml_id": xml_id,
        "surname": surname,
        "forename": forename,
        "name_full": name_full,
        "birth": birth,
        "death": death,
        "note": note,
        "role": role,
        "gnd_uri": gnd_uri,
        "gnd_id": gnd_id if gnd_id else None,
        "source_file": source_file,
        "in_group": 1 if in_group else 0,
    }


def extract_all_persons(register_dir: Path) -> list[dict]:
    """Parse all person register XML files."""
    persons = []

    for xml_file in sorted(register_dir.glob("*.xml")):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        fname = xml_file.name

        # Top-level persons (direct children of the main listPerson)
        main_list = root.find(".//tei:listPerson", TEI_NS)
        if main_list is None:
            continue

        for child in main_list:
            tag = child.tag.replace(f"{{{TEI_NS['tei']}}}", "")

            if tag == "person":
                persons.append(parse_person(child, fname, in_group=False))

            elif tag == "listPerson":
                # Nested group (family etc.)
                for person_elem in child.findall("tei:person", TEI_NS):
                    persons.append(parse_person(person_elem, fname, in_group=True))

    return persons


def load_persons_to_db(conn: sqlite3.Connection, persons: list[dict]):
    """Insert persons into the database (replace on conflict)."""
    conn.executemany(
        """INSERT OR REPLACE INTO persons
           (xml_id, surname, forename, name_full, birth, death, note,
            role, gnd_uri, gnd_id, source_file, in_group)
           VALUES (:xml_id, :surname, :forename, :name_full, :birth, :death, :note,
                   :role, :gnd_uri, :gnd_id, :source_file, :in_group)""",
        persons,
    )
    conn.commit()
    print(f"  Loaded {len(persons)} persons into database.")


# ---------------------------------------------------------------------------
# Step 2: Query GND API
# ---------------------------------------------------------------------------


def make_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def map_gnd_gender(gender_info: list | None) -> tuple[str, str, str]:
    """
    Map GND gender field to our categories.

    Returns:
        (gender_id, gender_label, gender_mapped)
    """
    if not gender_info or not isinstance(gender_info, list) or len(gender_info) == 0:
        return ("", "", "unknown")

    entry = gender_info[0]
    gender_id = entry.get("id", "")
    gender_label = entry.get("label", "")

    if "male" in gender_id.lower() and "female" not in gender_id.lower():
        mapped = "male"
    elif "female" in gender_id.lower():
        mapped = "female"
    else:
        mapped = "unknown"

    return (gender_id, gender_label, mapped)


def query_gnd_api(conn: sqlite3.Connection, session: requests.Session):
    """Query the GND API for all persons with GND IDs not yet queried."""

    # Get GND IDs that we haven't queried yet
    cursor = conn.execute(
        """
        SELECT DISTINCT p.gnd_id
        FROM persons p
        WHERE p.gnd_id IS NOT NULL
          AND p.gnd_id NOT IN (SELECT gnd_id FROM gnd_ground_truth)
    """
    )
    pending = [row[0] for row in cursor.fetchall()]

    if not pending:
        print("  All GND entries already queried. Nothing to do.")
        return

    print(f"  Querying GND API for {len(pending)} entries...")

    from datetime import datetime, timezone

    for i, gnd_id in enumerate(pending):
        url = f"{GND_API_BASE}/{gnd_id}.json"

        try:
            resp = session.get(url, timeout=15)
            status = resp.status_code

            if status == 200:
                data = resp.json()

                # Extract fields
                gender_id, gender_label, gender_mapped = map_gnd_gender(
                    data.get("gender")
                )
                types = json.dumps(
                    [t for t in data.get("type", []) if t != "AuthorityResource"]
                )
                preferred_name = data.get("preferredName", "")

                professions = data.get("professionOrOccupation", [])
                prof_labels = (
                    json.dumps([p.get("label", "") for p in professions])
                    if professions
                    else "[]"
                )

                dob = (
                    data.get("dateOfBirth", [""])[0] if data.get("dateOfBirth") else ""
                )
                dod = (
                    data.get("dateOfDeath", [""])[0] if data.get("dateOfDeath") else ""
                )

                conn.execute(
                    """INSERT OR REPLACE INTO gnd_ground_truth
                       (gnd_id, gnd_gender_id, gnd_gender_label, gnd_gender_mapped,
                        gnd_type, gnd_preferred_name, gnd_profession,
                        gnd_date_of_birth, gnd_date_of_death,
                        http_status, raw_json, queried_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        gnd_id,
                        gender_id,
                        gender_label,
                        gender_mapped,
                        types,
                        preferred_name,
                        prof_labels,
                        dob,
                        dod,
                        status,
                        json.dumps(data, ensure_ascii=False),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            else:
                # Store failed lookup so we don't retry endlessly
                conn.execute(
                    """INSERT OR REPLACE INTO gnd_ground_truth
                       (gnd_id, gnd_gender_mapped, http_status, queried_at)
                       VALUES (?, ?, ?, ?)""",
                    (gnd_id, "error", status, datetime.now(timezone.utc).isoformat()),
                )

        except Exception as e:
            print(f"    Error for {gnd_id}: {e}")
            conn.execute(
                """INSERT OR REPLACE INTO gnd_ground_truth
                   (gnd_id, gnd_gender_mapped, http_status, queried_at)
                   VALUES (?, ?, ?, ?)""",
                (gnd_id, "error", -1, datetime.now(timezone.utc).isoformat()),
            )

        # Commit every 50 entries for resumability
        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"    {i + 1}/{len(pending)} done...")

        time.sleep(REQUEST_DELAY)

    conn.commit()
    print(f"  Done. Queried {len(pending)} GND entries.")


# ---------------------------------------------------------------------------
# Step 3: Print summary
# ---------------------------------------------------------------------------


def print_summary(conn: sqlite3.Connection):
    """Print database summary stats."""
    print("\n" + "=" * 60)
    print("GROUND TRUTH DATABASE SUMMARY")
    print("=" * 60)

    total = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    with_gnd = conn.execute(
        "SELECT COUNT(*) FROM persons WHERE gnd_id IS NOT NULL"
    ).fetchone()[0]
    without_gnd = conn.execute(
        "SELECT COUNT(*) FROM persons WHERE gnd_id IS NULL"
    ).fetchone()[0]
    in_group = conn.execute(
        "SELECT COUNT(*) FROM persons WHERE in_group = 1"
    ).fetchone()[0]

    print(f"\nPersons register:")
    print(f"  Total persons:    {total:,}")
    print(f"  With GND URI:     {with_gnd:,}")
    print(f"  Without GND:      {without_gnd:,}")
    print(f"  In family groups: {in_group:,}")

    # GND ground truth stats
    queried = conn.execute("SELECT COUNT(*) FROM gnd_ground_truth").fetchone()[0]
    if queried > 0:
        print(f"\nGND ground truth ({queried:,} queried):")

        for row in conn.execute(
            """
            SELECT gnd_gender_mapped, COUNT(*) as cnt
            FROM gnd_ground_truth
            WHERE http_status = 200
            GROUP BY gnd_gender_mapped
            ORDER BY cnt DESC
        """
        ):
            print(f"  {row[0]:12s} {row[1]:,}")

        errors = conn.execute(
            "SELECT COUNT(*) FROM gnd_ground_truth WHERE http_status != 200"
        ).fetchone()[0]
        if errors:
            print(f"  {'errors':12s} {errors:,}")

        # Type breakdown
        print(f"\nGND entity types (persons with gender):")
        for row in conn.execute(
            """
            SELECT gnd_gender_mapped, COUNT(*) as cnt
            FROM gnd_ground_truth
            WHERE http_status = 200 AND gnd_gender_mapped != 'unknown'
            GROUP BY gnd_gender_mapped
            ORDER BY cnt DESC
        """
        ):
            pct = row[1] / queried * 100
            print(f"  {row[0]:12s} {row[1]:,} ({pct:.1f}%)")

        no_gender = conn.execute(
            """
            SELECT COUNT(*) FROM gnd_ground_truth
            WHERE http_status = 200 AND (gnd_gender_id = '' OR gnd_gender_id IS NULL)
        """
        ).fetchone()[0]
        print(f"  {'no gender':12s} {no_gender:,} ({no_gender/queried*100:.1f}%)")
        print(f"    (likely organisations, conferences, etc.)")

    print(f"\nDatabase: {DB_PATH}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Building ground truth database for genderTagger")
    print("=" * 60)

    # Step 1: Parse XML
    print("\n[1/3] Parsing TEI-XML person register...")
    persons = extract_all_persons(REGISTER_DIR)
    print(f"  Found {len(persons)} persons in {REGISTER_DIR}")

    # Step 2: Load into DB
    print("\n[2/3] Loading into SQLite...")
    conn = init_db(DB_PATH)
    load_persons_to_db(conn, persons)

    # Step 3: Query GND
    print("\n[3/3] Querying GND API for ground truth...")
    session = make_session()
    query_gnd_api(conn, session)

    # Summary
    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
