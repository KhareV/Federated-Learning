# Canonical Hashing Rule

All T001 and future artifact hashes use SHA-256 and lowercase hexadecimal output. Files are hashed
as their exact bytes. Byte strings are hashed without transformation. JSON-compatible data is
serialized as UTF-8 with lexicographically sorted keys, compact separators (`,` and `:`), preserved
Unicode, and non-standard NaN/Infinity values rejected before SHA-256 hashing. This convention is
implemented only in `src/nhm/hashing.py` and must not be forked into a second convention.

`reports/t001/artifact_hashes.json` never includes itself, which prevents a circular digest.

