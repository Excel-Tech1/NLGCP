# Southern Nigeria NIGNET audit

This package inventories local archives without modifying source files. ZIP
members are read in place and SHA-256 hashed while streamed. The optional ZIP
extractor refuses traversal, links, special files, overwrites, and insufficient
disk space. RINEX header `APPROX POSITION XYZ` values are classified as
**PROVISIONAL** unless a separately sourced record identifies a coordinate
frame, epoch, and authoritative source.

Run from the repository root:

```sh
PYTHONPATH=research/southern_network_audit/src .venv/bin/python -m nlgcp_southern_audit.cli \
  --archive /home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip \
  --output-root /home/excellence/nlgcp-data/validation/southern-nignet \
  --station-registry /home/excellence/nlgcp-data/metadata/station_registry.csv
```

The pipeline is an inventory, coverage, and geometry assessment only. It does
not run positioning, generate corrections, or claim positioning accuracy.
Header window overlap is explicitly not an observed common epoch count.
