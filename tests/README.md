# Testing

- `unit/`: fast isolated tests.
- `integration/`: dependency and service-boundary tests.
- `fixtures/`: small, licensed fixtures only. Synthetic material must be labelled `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`.

`make check` is the local quality gate. `make health` reports live development dependency status and distinguishes `HEALTHY`, `FAILED`, and `NOT INSTALLED`.
