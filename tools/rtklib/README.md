# RTKLIB Integration Scaffold

RTKLIB will provide documented, validated RTK functionality. NLGCP will not replace it with speculative implementations or silently use modified forks.

**Phase 1 status:** a host `rnx2rtkp` executable responds to `--help`, but its exact upstream commit and build provenance are unresolved. Treat it as an external dependency, not a reproducible verified installation. Nothing is vendored. Select and record an upstream release/commit only during a reviewed dependency decision. Canonical source: the official RTKLIB repository maintained by Tomoji Takasu (`https://github.com/tomojitakasu/RTKLIB`).

Planned repeatable procedure:

1. Record the approved upstream URL, immutable commit/tag, license, and source checksum in a dependency manifest.
2. Clone into a directory outside tracked source or use a checksum-verified archive.
3. Build the required console applications using its documented Linux build instructions.
4. Run `rnx2rtkp -h` (or the approved binary verification) and capture its version/build provenance.
5. Keep NLGCP patches isolated and reviewed; never modify the upstream checkout invisibly.

Later integration will call verified RTKLIB tools/libraries from reproducible experiment manifests. Host availability is not a scientific validation claim.
