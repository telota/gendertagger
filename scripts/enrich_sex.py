#!/usr/bin/env python3
"""Enrich TEI Personen Register XML files with <sex> elements from gender classification data.

Data model:
  <sex value="male|female" evidence="assigned" resp="#fko|#gendertagger" cert="high|low"/>

Placement: After the last <persName> child of each <person>, before <birth>/<death>/<note>/etc.

Rules:
  - value: corrected_gender if non-empty, else predicted_gender
  - Skip entries where value is not 'male' or 'female' (unknown, institution, empty)
  - evidence: always 'assigned' (historical assignment, not self-identification)
  - resp: '#fko' if review_status is 'corrected' or 'verified' (human-reviewed)
          '#gendertagger' if unreviewed (automated ensemble)
  - cert: 'high' if human-reviewed or automated with cert='high'
          'low'  if automated with cert='single'
"""

import argparse
import csv
import os
import re
import sys
from lxml import etree

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"


def load_gender_data(csv_path):
    """Load gender classification data from CSV, keyed by xml_id."""
    data = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data[row["xml_id"]] = row
    return data


def get_sex_attrs(row):
    """Determine <sex> element attributes from a CSV row.

    Returns a dict of attributes, or None if the entry should be skipped.
    """
    sex_val = (
        row.get("corrected_gender", "").strip()
        or row.get("predicted_gender", "").strip()
    )
    if sex_val not in ("male", "female"):
        return None

    review_status = row.get("review_status", "").strip()
    if review_status in ("corrected", "verified"):
        return dict(value=sex_val, evidence="assigned", resp="#fko", cert="high")
    else:
        cert = "high" if row.get("cert", "").strip() == "high" else "low"
        return dict(value=sex_val, evidence="assigned", resp="#gendertagger", cert=cert)


def find_insertions(xml_path, gender_data):
    """Parse one XML file to find where <sex> elements should be inserted.

    Uses lxml for structural parsing to identify:
    - Which <person> elements need a <sex> element
    - The sourceline of the element after the last <persName> child

    Returns a list of insertion descriptors and statistics.
    """
    parser = etree.XMLParser(
        remove_comments=False, remove_pis=False, remove_blank_text=False
    )
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()

    insertions = []
    stats = {
        "inserted": 0,
        "already": 0,
        "no_match": 0,
        "skipped_val": 0,
        "no_persname": 0,
    }

    for person in root.iter(f"{TEI}person"):
        xml_id = person.get(f"{XML_NS}id")
        if not xml_id:
            continue

        if person.find(f"{TEI}sex") is not None:
            if xml_id in gender_data:
                stats["already"] += 1
            continue

        if xml_id not in gender_data:
            stats["no_match"] += 1
            continue

        attrs = get_sex_attrs(gender_data[xml_id])
        if attrs is None:
            stats["skipped_val"] += 1
            continue

        # Find last <persName> direct child
        children = list(person)
        last_persname_idx = None
        for i, child in enumerate(children):
            if child.tag == f"{TEI}persName":
                last_persname_idx = i

        if last_persname_idx is None:
            stats["no_persname"] += 1
            continue

        # Determine the line before which to insert
        # (the first non-persName, non-PI/comment element after the last persName)
        insert_before_line = None
        for j in range(last_persname_idx + 1, len(children)):
            candidate = children[j]
            # Skip processing instructions and comments
            if callable(candidate.tag):
                continue
            insert_before_line = candidate.sourceline
            break

        insertions.append(
            {
                "insert_before_line": insert_before_line,
                "persname_start_line": children[last_persname_idx].sourceline,
                "person_start_line": person.sourceline,
                "attrs": attrs,
                "xml_id": xml_id,
            }
        )
        stats["inserted"] += 1

    return insertions, stats


def apply_insertions(xml_path, insertions, dry_run=False):
    """Apply insertions to the raw XML file using line-based string insertion.

    This preserves the original file formatting exactly, only adding new lines.
    """
    with open(xml_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    resolved = []
    for ins in insertions:
        # Determine indentation from the persName's start line
        pn_line = lines[ins["persname_start_line"] - 1]
        indent = re.match(r"^(\s*)", pn_line).group(1)

        if ins["insert_before_line"] is not None:
            insert_at = ins["insert_before_line"] - 1  # 0-based
            # Edge case: </persName> and next element on the same line
            # In this case, inserting a new line BEFORE would put sex inside persName.
            # Instead, split the line at </persName> and insert sex between.
            target_line = lines[insert_at]
            if "</persName>" in target_line:
                parts = target_line.split("</persName>", 1)
                lines[insert_at] = parts[0] + "</persName>\n"
                a = ins["attrs"]
                sex_line = (
                    f'{indent}<sex value="{a["value"]}" evidence="{a["evidence"]}" '
                    f'resp="{a["resp"]}" cert="{a["cert"]}"/>\n'
                )
                remainder = indent + parts[1].lstrip()
                lines.insert(insert_at + 1, remainder)
                lines.insert(insert_at + 1, sex_line)
                resolved.append(None)  # sentinel to skip normal insertion
                continue
        else:
            # No next element sibling after persName. Find </person>.
            insert_at = None
            for i in range(ins["persname_start_line"], len(lines)):
                if "</person>" in lines[i]:
                    insert_at = i
                    break
            if insert_at is None:
                print(
                    f"  WARNING: Could not find </person> for {ins['xml_id']}, skipping"
                )
                continue

        a = ins["attrs"]
        sex_line = (
            f'{indent}<sex value="{a["value"]}" evidence="{a["evidence"]}" '
            f'resp="{a["resp"]}" cert="{a["cert"]}"/>\n'
        )
        resolved.append((insert_at, sex_line, ins["xml_id"]))

    # Filter out sentinels (already handled inline)
    resolved = [r for r in resolved if r is not None]

    # Sort descending by line index so insertions don't shift subsequent indices
    resolved.sort(key=lambda x: x[0], reverse=True)

    if dry_run:
        for idx, sex_line, xml_id in sorted(resolved, key=lambda x: x[0]):
            print(f"  {xml_id}: would insert at line {idx + 1}: {sex_line.strip()}")
        return

    for idx, sex_line, _ in resolved:
        lines.insert(idx, sex_line)

    with open(xml_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )
    parser.add_argument("--csv", default=None, help="Path to gender_reviewed.csv")
    parser.add_argument(
        "--xml-dir", default=None, help="Path to Personen register directory"
    )
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    csv_path = args.csv or os.path.join(
        base, "..", "data", "output", "gender_reviewed.csv"
    )
    xml_dir = args.xml_dir or os.path.join(
        base, "..", "data", "raw", "schleiermacher", "Register", "Personen"
    )
    csv_path = os.path.normpath(csv_path)
    xml_dir = os.path.normpath(xml_dir)

    print(f"CSV:     {csv_path}")
    print(f"XML dir: {xml_dir}")
    if args.dry_run:
        print("MODE:    DRY RUN (no files will be modified)")
    print()

    gender_data = load_gender_data(csv_path)
    print(f"Loaded {len(gender_data)} entries from CSV")
    print()

    total = {
        "inserted": 0,
        "already": 0,
        "no_match": 0,
        "skipped_val": 0,
        "no_persname": 0,
    }

    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        xml_path = os.path.join(xml_dir, f"{letter}.xml")
        if not os.path.exists(xml_path):
            continue

        insertions, stats = find_insertions(xml_path, gender_data)

        if insertions:
            print(
                f"{letter}.xml: {stats['inserted']} to insert, "
                f"{stats['skipped_val']} skipped (value), "
                f"{stats['no_match']} unmatched"
            )
            apply_insertions(xml_path, insertions, dry_run=args.dry_run)

        for k in total:
            total[k] += stats[k]

    print()
    print("=== Summary ===")
    print(f"  Inserted:                        {total['inserted']}")
    print(f"  Already had <sex>:               {total['already']}")
    print(f"  No CSV match (not in analysis):  {total['no_match']}")
    print(f"  Skipped (unknown/institution):   {total['skipped_val']}")
    print(f"  Skipped (no <persName> found):   {total['no_persname']}")


if __name__ == "__main__":
    main()
