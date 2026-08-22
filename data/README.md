# Data Policy

`data/raw` is immutable. Never edit raw GNSS observations in place; record provenance and place derived artifacts in `data/processed` or a versioned experiment location. Do not commit RINEX, RTCM, precise products, or large scientific datasets. `.gitkeep` files preserve the layout only.

Future approved source data will live in access-controlled object storage with checksums, provenance, retention policy, and immutable/versioned objects. Unavailable real data must remain unavailable; never silently replace it with mock data. Synthetic test fixtures must say `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`.
