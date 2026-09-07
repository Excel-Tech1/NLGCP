# Phase 3 Single-Base RTK Pipeline

This package prepares and executes reproducible single-base RTK experiments around
the pinned RTKLIB `rnx2rtkp` executable. It does not implement an RTK estimator.

Real scientific execution is fail-closed until the Phase 2 input gate is complete:
verified station identities, coordinates, reference frame/epoch, equipment
intervals, real observations, navigation data, overlapping intervals, provenance,
hashes, and an approved Phase 2 audit.

Outputs are written under:

```text
${NLGCP_DATA_ROOT}/processed/single-base/<experiment-id>/
```

Dry-run preparation may create manifests, RTKLIB configuration, reports, and
input hash records without running RTKLIB. Synthetic tests are explicitly labelled
and are not scientific evidence.
