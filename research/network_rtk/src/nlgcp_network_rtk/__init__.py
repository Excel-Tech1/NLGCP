"""NLGCP Phase 5 offline network RTK engine.

Phase 5 evaluates multi-reference-station geometry and independent
baseline inputs.  It does NOT produce atmospheric corrections (Phase 6)
or virtual observations (Phase 7).  Averages of independent baselines
are labelled network-input aggregates, never VRS solutions.
"""

ENGINE_VERSION = "0.1.0"
EXPERIMENT_SCHEMA_VERSION = "1.0"
ADMISSION_SCHEMA_VERSION = "1.0"
GEOMETRY_SCHEMA_VERSION = "1.0"
OVERLAP_SCHEMA_VERSION = "1.0"
METRICS_SCHEMA_VERSION = "1.0"

# Minimum admitted reference stations for a network experiment.  Three is
# the smallest count that forms a triangle/polygon around (or alongside) a
# rover and therefore the smallest geometry that can support later Phase 6
# spatial modelling.  The requirement is recorded in every experiment
# definition and validation output; geometry adequacy (extent, enclosing,
# distances) is assessed separately and may BLOCK an experiment even when
# the count is met.
MIN_REFERENCE_STATIONS = 3
