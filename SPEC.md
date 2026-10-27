# Eclipse Warranty — SPEC v0.1

- Date: 2026-10-26 · Status: SPEC + BUILD v0.1 (this pass) · Builder: Silas (W-002) · Bench: separate agent (Verity) — builder does not certify own work.
- Source: Argus suggestions 2026-10-26 #9 (`argus-suggestions-20261026.md`); owner adopted all 10.
- Repo: `eclipse-warranty-mcp` · Server name: `io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-warranty-mcp`
- Scope label: **LOCAL / fixture** — see §2.

## 1. Product definition

Warranty registration witness for agent purchases — binds serial, buyer mandate, and retailer receipt into one transferable claim pack.

- Buyer: shoppers' agents and merchants (funnel into Eclipse Procure).
- Pricing: **FREE + funnel role** — free registration drives Eclipse Procure order volume and Till receipts. No payment anything: no payment tool, field, or flow in v0.1.

## 2. Scope — legally-clear, labelled truthfully

- LOCAL/fixture scope only: registrations operate on fixture purchase records supplied by the caller (refs/strings the caller asserts; no retailer, manufacturer, or payment network is contacted).
- Seals are local hash seals: HMAC-SHA256 with a local demo key file (`keys/demo.key`, generated at runtime, gitignored, clearly labelled demo) over canonical JSON.
- The pack is a **witness record, not a warranty contract**. This product makes NO claim of legal warranty adjudication, coverage, eligibility, or enforceability. It witnesses that a set of bindings was sealed together and has not been altered since.
- No live retailer/manufacturer integration, no claim filing with any third party, no adjudication in v0.1.

## 3. Novel mechanism (the claim the bench must test exactly)

**The claim pack is transferable on resale because it is bound to the product serial + sealed purchase proof, not to a retailer account login.**

Concretely in the build:
- Immutable bindings at registration: `serial`, `product_ref`, `buyer_mandate_ref`, `retailer_receipt_ref`, `purchase_ts`.
- `current_holder` is a mutable, chained field — NOT a binding. Transfer appends a chained transfer record and re-seals; it never edits the original bindings.
- `verify_pack` recomputes the seal from serial + bindings + transfer chain alone. It takes no account credential, login, or original-holder proof. A pack therefore verifies after transfer **without the original holder participating or existing**.
- Tampering with any bound field, the holder, or any transfer record breaks the seal → `INVALID`.

## 4. N-check vs incumbents

| | Extend / Mulberry | Eclipse Warranty v0.1 |
|---|---|---|
| Attachment | Retailer-attached plan at checkout | Independent witness pack, registered by the buyer's agent |
| Binding | Retailer account login | Product serial + sealed purchase proof (mandate ref + receipt ref) |
| Agent mandate proof | None | `buyer_mandate_ref` is a sealed binding |
| Transfer on resale | Account-bound; transfer constrained by account | Chained transfer record; validity survives transfer, no original-holder involvement |
| Adjudication | Plan administrator adjudicates | None — witness record only (§2) |

## 5. Tools — v0.1, exactly five

All responses carry `scope: "LOCAL/fixture"`, `seal_type: "HMAC-SHA256 demo (local key)"`.

### 5.1 `register_warranty`
Args: `serial`, `product_ref`, `buyer_mandate_ref`, `retailer_receipt_ref`, `purchase_ts` (all required strings), `holder_ref` (optional; defaults to `buyer_mandate_ref`).
Creates a sealed claim pack: `pack_id` (`EW-` + 16 hex of binding hash), all bindings, `current_holder`, empty `transfers[]`, `prev_hash: "GENESIS"` chain genesis, `seal`. One pack per serial: re-registering the same serial → refusal `SERIAL_ALREADY_REGISTERED`.

### 5.2 `get_pack`
Args: `pack_id`. Returns the full stored pack (bindings, holder, transfer chain, seal) or `PACK_NOT_FOUND`.

### 5.3 `verify_pack`
Args: `pack_id` (stored pack) OR `pack` (caller-supplied pack object). Recomputes the seal over canonical bindings + holder + transfer chain and checks chain linkage (genesis + each transfer's `prev_seal`). Returns `{valid: true, result: "VALID"}` or `{valid: false, result: "INVALID", reason}`. Tamper with any bound field = INVALID.

### 5.4 `transfer_pack`
Args: `pack_id`, `new_holder_ref`, `transfer_ref` (optional), `transferred_at` (optional ISO ts). Verifies the pack first (invalid pack → refusal `PACK_INVALID`, no transfer). Appends `{seq, from_holder, to_holder, transfer_ref, transferred_at, prev_seal}` and re-seals over the extended chain. Returns updated pack. Validity after transfer derives from the serial + purchase-proof chain, NOT any account identity.

### 5.5 `claim_check`
Args: `serial`, `pack_id` (optional). Answers whether a valid transferable claim pack exists for that serial: `{exists, valid, transferable, pack_id, current_holder}`. Unregistered serial → `{exists: false, valid: false, transferable: false}` — a plain negative, not an error.

## 6. State, seal, chain

- State: local JSON store `data/packs.json` (gitignored runtime state; env override `ECLIPSE_WARRANTY_DATA_DIR`). Fixture seeds live separately in `fixtures/`, never in `data/`.
- Seal: `HMAC-SHA256(demo_key, canonical_json({pack_id, bindings, current_holder, transfers}))`, canonical = sorted keys, compact separators. Demo key: 32 random bytes hex in `keys/demo.key` (gitignored, mode 0600, generated on first use if absent). Demo only — no production key claim.
- Chain: genesis `prev_hash = "GENESIS"`; each transfer records the seal it supersedes (`prev_seal`); verify walks the chain in order.

## 7. Non-goals (v0.1, by name)

No warranty adjudication or coverage decision · no retailer/manufacturer/payment integration · no payments or pricing logic · no accounts/logins · no legal-contract generation · no remote/hosted deployment · no claim filing with third parties.

## 8. Tests (bench will re-run)

`tests/test_warranty.py` (unittest, stdlib): seal verify · tamper detection per bound field (serial, product_ref, buyer_mandate_ref, retailer_receipt_ref, purchase_ts) · transfer preserves validity · transfer chain audit (linkage/order/multi-transfer) · unregistered serial = no pack · duplicate serial refusal · invalid pack cannot transfer.

## Addendum — Bench Fix D1/D2 (v0.1.1, 2026-10-26)

Appended after the Verity bench verdict on v0.1.0 (CONDITIONAL, local/fixture; defects D1 MEDIUM, D2 LOW). The sections above are the original v0.1 spec and are unchanged; this addendum supersedes §6's seal formula where they differ.

- **D1 → C1 (seal blind spot, closed with BOTH shapes).** (a) *Full-content seal:* the seal is now `HMAC-SHA256(demo_key, canonical_json(<complete pack object minus the seal field>))` — bindings (all keys, not the former 5-field projection), `current_holder`, `transfers`, `prev_hash`, `registered_at`, `scope`, and `seal_type` are sealed together; altering any of them breaks the seal. (b) *Strict structure at verify:* `verify_pack` returns INVALID for any pack carrying keys outside the specced sets (top-level pack fields, the 5 binding fields, the 6 transfer-record fields), missing specced fields, non-string field values, or a `scope`/`seal_type` outside the spec vocabulary (scope must be exactly `LOCAL/fixture`). A pack with `bindings.injected_coverage` injected or `scope` relabelled `LIVE/production` therefore verifies INVALID, supplied or stored. `get_pack` refuses structurally out-of-spec stored packs (`PACK_INVALID`) rather than serving injected/relabelled content as sealed pack content. Consequence: packs sealed under v0.1.0's projected seal verify INVALID under v0.1.1 — acceptable at LOCAL/fixture scope; no migration (fixtures are re-registered).
- **D2 → C2 (schema enforcement).** `dispatch` in `server.py` now validates arguments against each tool's advertised input schema before calling it: required fields must be present, declared types are exact (a non-string where a string is declared — e.g. int `purchase_ts`, list `serial` — is a clean validation error, never coerced), and unknown/extra argument keys are rejected per `additionalProperties: false`. The store layer also dropped its silent `str()` coercions and type-checks its string fields directly.
- **Regression coverage.** `tests/test_warranty.py` replicates both bench repros at store level and over the wire (stdio JSON-RPC): injected bindings/top-level/transfer keys → INVALID + `get_pack` refusal, scope relabel → INVALID + refusal, `registered_at` tamper → INVALID, int `purchase_ts` / list `serial` / extra fields → clean errors with nothing registered. Suite: 28 tests (14 pre-existing, all still passing, + 14 new).

— Eclipse Warranty · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
