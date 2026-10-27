# BUILD RECORD — v0.1 (2026-10-26)

**Status: BUILT, pre-bench. STOP — Verity benches next; no self-certification.**
Builder: Silas (W-002) · Spec: `SPEC.md` · Scope label: **LOCAL / fixture**

## What was built

Python 3 stdlib only, MCP over stdio JSON-RPC (`initialize`, `tools/list`, `tools/call`), five tools closed surface:

- `register_warranty` — binds serial + product_ref + buyer_mandate_ref + retailer_receipt_ref + purchase_ts; creates sealed pack (`EW-…` id, chain genesis `prev_hash: "GENESIS"`); one pack per serial (`SERIAL_ALREADY_REGISTERED`).
- `get_pack` — full pack retrieval (`PACK_NOT_FOUND`).
- `verify_pack` — recomputes HMAC seal over canonical bindings + holder + transfer chain, audits chain linkage; tamper with any bound field = `INVALID`. Accepts `pack_id` or a supplied pack object; needs no account/original holder.
- `transfer_pack` — verifies first (`PACK_INVALID` refuses), appends chained transfer record `{seq, from_holder, to_holder, transfer_ref, transferred_at, prev_seal}`, re-seals. Bindings never edited.
- `claim_check` — exists/valid/transferable for a serial; unregistered serial = plain negative.

Novel mechanism implemented as specced (SPEC §3): transferability derives from serial + sealed purchase proof; `current_holder` is a chained field, not a binding.

## Seal / state

- HMAC-SHA256 over canonical JSON, local **demo** key generated at runtime → `keys/demo.key` (gitignored, 0600, never committed).
- State: `data/packs.json` (gitignored; `ECLIPSE_WARRANTY_DATA_DIR` override). Fixture seed separate: `fixtures/sample_purchase.json`.
- No payment anything. No adjudication claim: pack = witness record, not a warranty contract.

## Verification at build

- Suite: 14/14 pass (`python3 -m unittest discover -s tests`) — seal verify, tamper per bound field (5 subtests), tamper holder/seal/transfer-record, transfer preserves validity, transfer chain audit (2 transfers, prev_seal linkage), invalid pack cannot transfer, claim_check registered/after-transfer, unregistered serial = no pack, duplicate serial refusal, get roundtrip.
- Stdio smoke: initialize (server name `io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-warranty-mcp`), exactly 5 tools listed, register → claim_check `transferable: true`, unknown tool → `NO_SUCH_TOOL`. Smoke ran against /tmp state; repo `data/` stayed empty.
- Secret sweep before first commit: grep for key/token/secret/password material — only the demo-key *mechanism* (runtime-generated, gitignored path); no key material in tree.

## Files

SPEC.md · README.md · server.json · LICENSE (MIT) · config.py · errors.py · warranty.py · server.py · tests/test_warranty.py · fixtures/sample_purchase.json · .gitignore (data/, __pycache__, *.env, keys/)
SPEC copy: `~/workspace/cyan-eclipse/argus-batch-20261026/specs/eclipse-warranty-mcp-SPEC.md`
