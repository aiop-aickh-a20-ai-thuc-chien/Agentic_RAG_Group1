# Lexical Near-Duplicate Layers

Target home for token, shingle, and fingerprint strategies.

Responsibilities:

- Compare chunks by surface text similarity.
- Keep thresholds conservative for ingestion-time metadata.
- Avoid repeating pairs already detected by exact matching.

Planned strategies:

- SimHash for compact fingerprints and fast Hamming-distance checks.
- MinHash for Jaccard-style shingle similarity and future LSH scaling.
