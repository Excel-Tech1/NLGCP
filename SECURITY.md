# Security Policy

Report vulnerabilities privately to the project maintainers; do not open a public issue containing exploit details or credentials. Until a private project contact is published, contact the repository owner through the hosting platform's private security reporting channel.

- Never commit passwords, tokens, private keys, real NTRIP credentials, certificates, or `.env`.
- Treat raw GNSS observations, partner endpoints, and station operational metadata according to their provider agreements.
- Use least privilege, pin/review dependencies, and address automated security findings promptly.
- PostgreSQL, NATS, and Redis bindings in this development compose file are for localhost only; never expose them directly to the public Internet.
- Production architecture must separate the user/control plane from the correction/data plane.
- Rotate any accidentally disclosed credential immediately and remove it from history with coordinated maintainer review.

Phase 1 defaults are development-only and are not production security controls.
