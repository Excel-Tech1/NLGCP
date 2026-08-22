# PRIDE PPP-AR Integration Scaffold

PRIDE PPP-AR is intended for offline precise processing, CORS coordinate checking, and independent scientific validation. It is not the production correction engine.

**Phase 1 status:** a host `pdp3` executable reports PRIDE PPP-AR 3.2.8, but its installation provenance has not been captured. It remains an external dependency and is not vendored. Select an immutable official release/commit and comply with its documentation and license before a reproducible installation. Canonical project information and acquisition must be verified with the PRIDE Lab maintainers.

Processing also requires externally acquired precise orbit/clock, bias, Earth-orientation, antenna, and related products appropriate to the experiment. Record their authoritative sources, versions, checksums, reference frames, and licenses.

Verification after reviewed installation must capture the executable/version output and reproduce an official example before any NLGCP dataset is used. No installation or scientific result is claimed here.
