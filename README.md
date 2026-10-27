# Eclipse Warranty

Warranty registration witness for agent purchases — binds serial, buyer mandate, and retailer receipt into one transferable claim pack.

**Status: v0.1.1 — bench fix round D1/D2 applied (full-content seal + strict pack structure; advertised schemas enforced at dispatch), re-bench pending.** Spec: `SPEC.md` (see its Bench Fix addendum). Scope: **LOCAL / fixture**.

## Novel mechanism

The claim pack is transferable on resale because it is bound to the product serial + sealed purchase proof, not to a retailer account login. Transfer appends a chained record and re-seals; verification recomputes the seal from the serial, bindings, and transfer chain alone — no account credential, no original holder. Incumbents (Extend / Mulberry) attach plans to retailer accounts with no agent mandate proof; here `buyer_mandate_ref` is a sealed binding.

## Honest scope

Registrations operate on fixture purchase records supplied by the caller. Seals are local HMAC-SHA256 hash seals using a demo key generated at runtime in `keys/` (gitignored). The pack is a **witness record, not a warranty contract** — no legal warranty adjudication, coverage, or enforceability is claimed, and no retailer or manufacturer is contacted.

## Tools (exactly five)

| Tool | What it does |
|---|---|
| `register_warranty` | Seal serial + product ref + buyer mandate ref + retailer receipt ref + purchase ts into a claim pack (chain genesis). One pack per serial. |
| `get_pack` | Retrieve a pack with all bindings, current holder, and transfer chain. |
| `verify_pack` | Recompute seal + chain linkage by `pack_id` or supplied pack object. Tamper with any bound field → `INVALID`. |
| `transfer_pack` | Re-bind to a new holder with a chained transfer record; pack verifies afterwards without the original holder. |
| `claim_check` | Given a serial (+ optional pack_id), answer whether a valid transferable claim pack exists. Unregistered serial → plain negative. |

## Pricing

FREE + funnel role — free registration drives Eclipse Procure order volume and Till receipts. No payment anything.

## Run

```
python3 server.py                          # MCP over stdio
python3 -m unittest discover -s tests -v
```

State: `data/packs.json` (gitignored; override `ECLIPSE_WARRANTY_DATA_DIR`). Demo key: `keys/demo.key` (gitignored, generated on first use; override `ECLIPSE_WARRANTY_KEY_FILE`). Fixture seeds: `fixtures/`.

MIT License · Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
