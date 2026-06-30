# Detection Layers

Target home for duplicate-detection algorithms.

Current implementations still live in the flat package to preserve imports:

- `dedup_detect.exact`
- `dedup_detect.simhash`
- `dedup_detect.embedding`

Move code here only after focused tests cover the old behavior and compatibility
exports are in place.
