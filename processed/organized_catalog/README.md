# Organized Model Catalog

This is the canonical organized view for this workspace.

- Generated at: `2026-05-29T12:50:14.731287+00:00`
- Official API models: `120`
- Internal official slots: `42`
- Internal official-family related: `325`
- Internal experimental-only: `1271`
- API models without internal signal: `89`

## Buckets

- `official_api_models.*`: raw official models returned by `/v1/models`.
- `internal_official_slots.*`: internal names that directly map to official API models or `mainline` slots.
- `internal_official_family_related.*`: internal names that still look tied to an official public family, but are not direct official IDs.
- `internal_experimental.*`: internal-only names that look like experiments, campaigns, feature branches, or research buckets.
- `api_without_internal_signal.*`: official API IDs that do not clearly show up in the internal list.

## Suggested Reading Order

1. `summary.json`
2. `internal_official_slots.txt`
3. `internal_official_family_related.txt`
4. `internal_experimental.txt`
5. `api_without_internal_signal.txt`
