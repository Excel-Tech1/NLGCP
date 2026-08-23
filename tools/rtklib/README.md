# RTKLIB Integration Scaffold

RTKLIB will provide documented, validated RTK functionality. NLGCP will not replace it with speculative implementations or silently use modified forks.

**Phase 1 closure status:** RTKLIB provenance was resolved to the official RTKLIB
repository, tag `v2.4.2-p13`, commit
`71db0ffa0d9735697c6adfd06fdf766d0e5ce807`. The installed host
`rnx2rtkp` at `/home/excellence/.local/bin/rnx2rtkp` hashes to
`b4a96cd0d5ffc00b44dab3a4fda214318c9f69cccee52128aec8bc26ad4f7d21` and
matched the source-tree build during Phase 1 evidence capture. RTKLIB remains an
external dependency; do not silently replace or upgrade it.

Planned repeatable procedure:

1. Record the approved upstream URL, immutable commit/tag, license, and source checksum in a dependency manifest.
2. Clone into a directory outside tracked source or use a checksum-verified archive.
3. Build the required console applications using its documented Linux build instructions.
4. Run `rnx2rtkp -h` (or the approved binary verification) and capture its version/build provenance.
5. Keep NLGCP patches isolated and reviewed; never modify the upstream checkout invisibly.

Phase 3 integration calls the verified `rnx2rtkp` executable from reproducible
experiment manifests. Host availability and synthetic smoke tests are not
scientific validation claims.
