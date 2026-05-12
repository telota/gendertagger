#!/usr/bin/env python3
"""Transform <persName> → <orgName> for institution entities across all XML files.

Uses Python regex (not lxml serialization) to avoid unwanted formatting changes.
Reads institution IDs from the generated Institutionen.xml register.

Three transformations:
  1. <persName key="INST">…</persName>  →  <orgName key="INST">…</orgName>
  2. <persName key="INST"/>              →  <orgName key="INST"/>
  3. <index … indexName="persons" corresp="INST">  →  indexName="institutions"

Multi-key handling (not currently needed but supported):
  <persName key="INST PERSON">…</persName>
  →  <orgName key="INST"><persName key="PERSON">…</persName></orgName>
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from lxml import etree

REGISTER_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "raw"
    / "schleiermacher"
    / "Register"
)
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "schleiermacher"
DEFAULT_REGISTER = REGISTER_DIR / "Institutionen.xml"

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"


def load_institution_ids(register_path: Path) -> set[str]:
    """Load institution IDs from Institutionen.xml (xml:id attributes of <org> elements)."""
    tree = etree.parse(str(register_path))
    ids = set()
    for org in tree.iter(f"{TEI}org"):
        xml_id = org.get(f"{XML_NS}id")
        if xml_id and xml_id != "TODO":
            ids.add(xml_id)
    return ids


def build_patterns(inst_ids: set[str]):
    """Build compiled regex patterns for the three transformations."""
    # Pattern 1: Normal persName with closing tag (DOTALL for multiline content)
    pat_normal = re.compile(
        r"<persName\b([^>]*)>([\s\S]*?)</persName>",
        re.DOTALL,
    )

    # Pattern 2: Self-closing persName
    pat_selfclose = re.compile(
        r"<persName\b([^/]*?)/>",
    )

    # Pattern 3: index elements with indexName="persons" and institution corresp
    # Build alternation of all institution IDs for matching
    id_alt = "|".join(re.escape(i) for i in sorted(inst_ids))
    pat_index = re.compile(
        r'(<index\b[^>]*)\bindexName="persons"([^>]*\bcorresp="(?:'
        + id_alt
        + r')"[^>]*>)',
    )

    return pat_normal, pat_selfclose, pat_index


def _extract_key(attrs_str: str) -> str | None:
    """Extract the value of key="..." from an attribute string."""
    m = re.search(r'\bkey="([^"]*)"', attrs_str)
    return m.group(1) if m else None


def _replace_key(attrs_str: str, new_key: str) -> str:
    """Replace the key="..." value in an attribute string."""
    return re.sub(r'\bkey="[^"]*"', f'key="{new_key}"', attrs_str)


def _remove_key(attrs_str: str) -> str:
    """Remove the key="..." attribute entirely from an attribute string."""
    # Remove key="..." and any surrounding extra spaces
    result = re.sub(r'\s*\bkey="[^"]*"', "", attrs_str)
    return result


def make_persname_callback(
    inst_ids: set[str], stats: Counter, is_selfclose: bool = False
):
    """Create a re.sub callback for persName → orgName transformation."""

    def callback(m):
        if is_selfclose:
            attrs = m.group(1)
        else:
            attrs = m.group(1)
            content = m.group(2)

        key_val = _extract_key(attrs)
        if not key_val:
            return m.group(0)  # No key attribute → skip

        keys = key_val.split()
        inst_keys = [k for k in keys if k in inst_ids]
        person_keys = [k for k in keys if k not in inst_ids]

        if not inst_keys:
            return m.group(0)  # No institution keys → skip

        if not person_keys:
            # All keys are institutions → simple rename
            stats["renamed"] += 1
            for k in inst_keys:
                stats[f"id:{k}"] += 1
            if is_selfclose:
                return f"<orgName{attrs}/>"
            else:
                return f"<orgName{attrs}>{content}</orgName>"
        else:
            # Mixed keys → wrap in orgName, keep inner persName with person keys
            stats["wrapped"] += 1
            for k in inst_keys:
                stats[f"id:{k}"] += 1
            inst_key_str = " ".join(inst_keys)
            person_key_str = " ".join(person_keys)
            inner_attrs = _replace_key(attrs, person_key_str)
            if is_selfclose:
                return (
                    f'<orgName key="{inst_key_str}"><persName{inner_attrs}/></orgName>'
                )
            else:
                return f'<orgName key="{inst_key_str}"><persName{inner_attrs}>{content}</persName></orgName>'

    return callback


def make_index_callback(stats: Counter):
    """Create a re.sub callback for index indexName="persons" → "institutions"."""

    def callback(m):
        stats["index_renamed"] += 1
        return m.group(1) + 'indexName="institutions"' + m.group(2)

    return callback


def transform_file(
    filepath: Path,
    pat_normal,
    pat_selfclose,
    pat_index,
    inst_ids: set[str],
    dry_run: bool,
) -> Counter:
    """Transform a single XML file. Returns stats counter."""
    stats = Counter()

    text = filepath.read_text(encoding="utf-8")
    original = text

    # Apply self-closing pattern FIRST (before normal pattern, to avoid partial matches)
    cb_selfclose = make_persname_callback(inst_ids, stats, is_selfclose=True)
    text = pat_selfclose.sub(cb_selfclose, text)

    # Apply normal persName pattern
    cb_normal = make_persname_callback(inst_ids, stats, is_selfclose=False)
    text = pat_normal.sub(cb_normal, text)

    # Apply index pattern
    cb_index = make_index_callback(stats)
    text = pat_index.sub(cb_index, text)

    if text != original:
        stats["files_modified"] = 1
        if not dry_run:
            filepath.write_text(text, encoding="utf-8")

    return stats


def validate_wellformedness(filepath: Path) -> bool:
    """Check if a file is well-formed XML (read-only, no serialization)."""
    try:
        etree.parse(str(filepath))
        return True
    except etree.XMLSyntaxError as e:
        print(f"  XML ERROR in {filepath}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Transform <persName> → <orgName> for institution entities in TEI XML files.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Root directory to walk for XML files (default: data/raw/schleiermacher/)",
    )
    parser.add_argument(
        "--register",
        type=Path,
        default=DEFAULT_REGISTER,
        help="Path to Institutionen.xml register file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate well-formedness of modified files after transformation",
    )
    parser.add_argument(
        "--exclude-dir",
        type=str,
        action="append",
        default=[],
        help="Directory names to exclude (can be repeated)",
    )
    args = parser.parse_args()

    if not args.register.exists():
        print(f"Error: Register file not found: {args.register}", file=sys.stderr)
        sys.exit(1)

    if not args.dir.exists():
        print(f"Error: Directory not found: {args.dir}", file=sys.stderr)
        sys.exit(1)

    # Load institution IDs
    inst_ids = load_institution_ids(args.register)
    print(f"Loaded {len(inst_ids)} institution IDs from {args.register.name}")

    # Build patterns
    pat_normal, pat_selfclose, pat_index = build_patterns(inst_ids)

    # Exclude the Institutionen.xml itself and Personen register (already cleaned)
    exclude_dirs = set(args.exclude_dir) | {"Personen"}
    exclude_files = {"Institutionen.xml"}

    # Gather XML files
    xml_files = []
    for p in sorted(args.dir.rglob("*.xml")):
        if p.name in exclude_files:
            continue
        if any(ex in p.parts for ex in exclude_dirs):
            continue
        xml_files.append(p)

    print(f"Scanning {len(xml_files)} XML files in {args.dir}")
    if args.dry_run:
        print("DRY RUN — no files will be modified\n")

    # Process files
    total_stats = Counter()
    modified_files = []
    validation_errors = []

    for filepath in xml_files:
        stats = transform_file(
            filepath,
            pat_normal,
            pat_selfclose,
            pat_index,
            inst_ids,
            args.dry_run,
        )
        if stats.get("files_modified"):
            rel = filepath.relative_to(args.dir)
            renamed = stats["renamed"]
            wrapped = stats["wrapped"]
            idx = stats["index_renamed"]
            parts = []
            if renamed:
                parts.append(f"{renamed} renamed")
            if wrapped:
                parts.append(f"{wrapped} wrapped")
            if idx:
                parts.append(f"{idx} index")
            print(f"  {rel}: {', '.join(parts)}")
            modified_files.append(filepath)

            if args.validate and not args.dry_run:
                if not validate_wellformedness(filepath):
                    validation_errors.append(filepath)

        total_stats += stats

    # Summary
    print(f"\n{'DRY RUN ' if args.dry_run else ''}Summary:")
    print(f"  Files scanned:  {len(xml_files)}")
    print(f"  Files modified: {total_stats['files_modified']}")
    print(f"  persName → orgName (single/all-inst key): {total_stats['renamed']}")
    print(f"  persName wrapped in orgName (multi-key):  {total_stats['wrapped']}")
    print(f"  index persons → institutions:             {total_stats['index_renamed']}")

    # Per-ID breakdown
    id_counts = {k: v for k, v in total_stats.items() if k.startswith("id:")}
    if id_counts:
        print(f"\n  Per-institution-ID counts ({len(id_counts)} IDs matched):")
        for k in sorted(id_counts, key=lambda x: id_counts[x], reverse=True):
            print(f"    {k[3:]}: {id_counts[k]}")

    if validation_errors:
        print(
            f"\n  WARNING: {len(validation_errors)} files have XML errors after transformation!"
        )
        for f in validation_errors:
            print(f"    {f.relative_to(args.dir)}")

    if args.dry_run:
        print("\nNo files were modified. Remove --dry-run to apply changes.")


if __name__ == "__main__":
    main()
