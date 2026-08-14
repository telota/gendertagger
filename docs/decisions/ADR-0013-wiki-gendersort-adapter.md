# ADR-0013: Wiki-Gendersort local-snapshot adapter

**Status:** Accepted

The direct-path snapshot selection in this decision is superseded by
[ADR-0023](ADR-0023-content-addressed-sqlite-method-lookups.md). The frozen name cleaning, native labels, and
normalization behavior remain accepted.

## Context

`wiki_gendersort` is the third Phase 5 method and the first name-based adapter that depends on a local
authority snapshot rather than a bundled library dictionary. The legacy pipeline resolved each forename
token against a `NamesOut.txt` table through Wiki-Gendersort's `nameclean` candidate generator and an
`assign` lookup, mapped the native `M`/`F`/`UNI`/`INI`/`UNK` label to the project alphabet, and reduced
per-token labels by the shared consensus. It reuses the name-based adapter pattern established in
[ADR-0012](ADR-0012-name-based-classifier-adapter-pattern.md) and the frozen `wiki_gendersort_v1` profile.
The transliteration dependency (`unidecode`) and the snapshot file are not needed by the core service.
See [methods and aggregation](../07-methods-and-aggregation.md).

## Decision

Port `nameclean` and `WikiGendersortTable.assign` verbatim: quoted and parenthetical text is moved to the
end, the name is split on non-letter characters, periods and fused initials are separated, hyphenated names
keep the compound and their parts, and surviving candidates are case-normalized with an appended
transliterated variant. `assign` returns the native label and the matched candidate. The native label is
mapped (`M`→`male`, `F`→`female`, `UNI`→`unisex`, `INI`→`no_name`, `UNK`→`unknown`), the mapped labels are
reduced by the Wiki-Gendersort priority consensus, and the raw label is normalized against the frozen
`wiki_gendersort_v1` profile. The adapter reports no `method_confidence`.

The `NamesOut.txt` snapshot is selected by required resolved run configuration (`names_db_path`), so the
exact authority table is recorded in run provenance. This is a direct filesystem path; the versioned
artifact/snapshot resolution hinted by the GND `snapshot` configuration is deferred to the GND adapter and
may later supersede the raw path. `unidecode` is the opt-in `wiki` extra, imported lazily; its absence
raises `MethodDependencyError` and fails the batch permanently. The lookup table backend is injectable for
testing and cached per snapshot path.

## Consequences

- Reproduces the legacy `wiki_gendersort` output exactly on all 8277 reference-corpus records.
- The snapshot path in resolved configuration makes the authority table reproducible from provenance;
  running without the path fails configuration resolution rather than silently using a default.
- Pure initials (`INI`) abstain through the shared `no_name` label, while `UNI` is a substantive
  `unknown`, preserving the abstain/unknown distinction.
- Core installs stay slim; `unidecode` is pulled only by the `wiki` extra.
- The direct-path configuration is provisional. When the GND adapter introduces versioned snapshot
  resolution, `wiki_gendersort` may adopt it under a new ADR; the raw label and normalization stay fixed.
