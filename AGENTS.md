# Codex / AI contributor instructions

## Project objective
Maintain the local feeding web app and the verified, read-only BOLOLO P50 Pro client. Keep any future Home Assistant integration small and evidence-based. Read `README.md` and `docs/CODEX_TASKS.md` before changing code.

## Workflow
- Work **directly on the existing `main` branch**. The owner explicitly requested no PR or feature branch.
- Keep architecture minimal. Avoid speculative interfaces, empty classes, elaborate plugin architectures, and unnecessary dependencies.
- Distinguish **verified facts**, **hypotheses**, **mock implementations**, and **blocked work** in docs and commit messages.
- Do not simulate device success or claim verified compatibility from fake responses. Unit tests with clearly labeled synthetic fixtures are encouraged.
- Implement a single independently runnable, read-only evidence collection/diagnostic capability first. Only then choose a HA integration strategy.
- Favor Python 3 standard library where sufficient; use dependencies only when they materially reduce complexity.
- Verify changes with available unit tests, lint/static checks, and clear manual setup instructions.
- If device-side evidence is absent, complete only safe offline tasks, document the exact evidence needed, and stop before speculative cloud commands.
- Always keep documentation consistent with actual implemented functionality.

## Appliance and physical safety
- Do not implement automated water dispensing or circumvent device locks/physical confirmation.
- Temperature write commands are gated on validated device semantics, safe limits, and user-authorized testing.
- No brute force, credential theft, TLS interception of unrelated services, or bypass of vendor safeguards.
- Never log credentials, bearer tokens, cookies, raw device IDs, or user-specific network topology.

## Secrets and repository hygiene
- This repo is private, but treat it as if it might be open sourced.
- Never commit raw pcaps, APKs, dumps, encrypted key material, tokens, secrets, household records, real site titles, or identifying network captures.
- Use environment variables, `.env.example` placeholders and sanitized/mocked fixtures.
- Do not put a cloud access token in issue descriptions, commit messages or test snapshots.

## Acceptance rule
An entity/command is 'supported' only if a redacted protocol record demonstrates the corresponding field/operation and a reproducible owner-run test confirms behavior. Cloud vs local transport must be empirically established. Port 8883 does not itself prove MQTT; app cellular control does not identify a cloud vendor.
