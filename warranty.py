#!/usr/bin/env python3
# Eclipse Warranty — claim-pack engine (LOCAL/fixture scope).
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
"""Sealed, transferable warranty claim packs.

Novel mechanism (SPEC §3): the pack is bound to the product serial +
sealed purchase proof (buyer mandate ref + retailer receipt ref +
purchase ts), NOT to a retailer account login. current_holder is a
chained, re-sealed field — never a binding — so verify_pack needs no
account credential and no original-holder participation.

Seal: HMAC-SHA256 with a local DEMO key (keys/demo.key, gitignored,
generated at runtime). Witness record only; no adjudication claim.
State: local JSON store in data/ (gitignored).
"""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

from config import SCOPE_LABEL, SEAL_TYPE
from errors import Refusal, ToolError

BOUND_FIELDS = ["serial", "product_ref", "buyer_mandate_ref",
                "retailer_receipt_ref", "purchase_ts"]
GENESIS = "GENESIS"
# Bench Fix D1 (v0.1.1): the seal covers the COMPLETE pack (every key
# except `seal` itself), and verify additionally rejects any pack whose
# structure leaves the specced sets / scope vocabulary below. An
# injected key or a relabelled scope can no longer ride the seal.
PACK_FIELDS = {"pack_id", "bindings", "current_holder", "transfers",
               "prev_hash", "registered_at", "scope", "seal_type",
               "seal"}
TRANSFER_FIELDS = {"seq", "from_holder", "to_holder", "transfer_ref",
                   "transferred_at", "prev_seal"}
ALLOWED_SCOPES = {SCOPE_LABEL}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class DemoKey:
    """Local demo HMAC key: generated at runtime, never committed."""

    def __init__(self, key_path):
        self.key_path = key_path

    def ensure(self):
        if not os.path.exists(self.key_path):
            os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
            raw = secrets.token_hex(32)
            fd = os.open(self.key_path,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(raw + "\n")
        with open(self.key_path) as f:
            return f.read().strip().encode()


def seal_payload(pack):
    # Full-content seal (Bench Fix D1): canonical form of the complete
    # pack object minus the seal field itself — bindings (all keys,
    # not a 5-field projection), holder, transfers, prev_hash,
    # registered_at, scope and seal_type are all sealed together.
    return {k: v for k, v in pack.items() if k != "seal"}


def pack_structure_errors(pack):
    """Out-of-spec structure: keys outside the specced sets, wrong
    field types, or a scope/seal_type outside the spec vocabulary.
    Any error means the pack carries content the seal never attested
    to as a specced pack -> INVALID at verify, refused at get_pack."""
    errs = []
    if not isinstance(pack, dict):
        return ["pack is not an object"]
    extra = sorted(set(pack) - PACK_FIELDS)
    if extra:
        errs.append("unknown pack field(s): " + ",".join(extra))
    missing = sorted(PACK_FIELDS - set(pack))
    if missing:
        errs.append("missing pack field(s): " + ",".join(missing))
    bindings = pack.get("bindings")
    if not isinstance(bindings, dict):
        errs.append("bindings is not an object")
    else:
        bextra = sorted(set(bindings) - set(BOUND_FIELDS))
        if bextra:
            errs.append("unknown bindings field(s): "
                        + ",".join(bextra))
        bmissing = sorted(set(BOUND_FIELDS) - set(bindings))
        if bmissing:
            errs.append("missing bindings field(s): "
                        + ",".join(bmissing))
        for k, v in bindings.items():
            if not isinstance(v, str):
                errs.append("bindings." + k + " is not a string")
    if pack.get("scope") not in ALLOWED_SCOPES:
        errs.append("scope label outside spec vocabulary: "
                    + repr(pack.get("scope")))
    if "seal_type" in pack and pack.get("seal_type") != SEAL_TYPE:
        errs.append("seal_type outside spec vocabulary: "
                    + repr(pack.get("seal_type")))
    for k in ("pack_id", "current_holder", "prev_hash",
              "registered_at", "seal"):
        if k in pack and not isinstance(pack[k], str):
            errs.append(k + " is not a string")
    transfers = pack.get("transfers")
    if not isinstance(transfers, list):
        errs.append("transfers is not a list")
    else:
        for i, t in enumerate(transfers):
            if not isinstance(t, dict):
                errs.append("transfers[%d] is not an object" % i)
                continue
            textra = sorted(set(t) - TRANSFER_FIELDS)
            if textra:
                errs.append("transfers[%d] unknown field(s): %s"
                            % (i, ",".join(textra)))
            tmissing = sorted(TRANSFER_FIELDS - set(t))
            if tmissing:
                errs.append("transfers[%d] missing field(s): %s"
                            % (i, ",".join(tmissing)))
    return errs


class WarrantyStore:
    def __init__(self, data_dir, key_path):
        self.data_dir = data_dir
        self.store_path = os.path.join(data_dir, "packs.json")
        self.key = DemoKey(key_path).ensure()

    # -- persistence -------------------------------------------------
    def _load(self):
        if not os.path.exists(self.store_path):
            return {"packs": {}}
        with open(self.store_path) as f:
            return json.load(f)

    def _save(self, data):
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.store_path)

    # -- seal --------------------------------------------------------
    def _seal(self, pack):
        msg = canonical(seal_payload(pack)).encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()

    def _pack_id(self, bindings):
        digest = hashlib.sha256(canonical(bindings).encode()).hexdigest()
        return "EW-" + digest[:16]

    # -- tools -------------------------------------------------------
    def register_warranty(self, args):
        missing = [k for k in BOUND_FIELDS if not args.get(k)]
        if missing:
            raise ToolError("missing required fields: " + ",".join(missing))
        # Bench Fix D2: no silent str() coercion — advertised string
        # fields must actually be strings (dispatch also enforces).
        for k in BOUND_FIELDS:
            if not isinstance(args[k], str):
                raise ToolError("field " + k + " must be a string")
        holder_ref = args.get("holder_ref")
        if holder_ref is not None and not isinstance(holder_ref, str):
            raise ToolError("field holder_ref must be a string")
        bindings = {k: args[k] for k in BOUND_FIELDS}
        data = self._load()
        for p in data["packs"].values():
            if p["bindings"]["serial"] == bindings["serial"]:
                raise Refusal(
                    "SERIAL_ALREADY_REGISTERED",
                    "serial already has pack " + p["pack_id"])
        pack = {
            "pack_id": self._pack_id(bindings),
            "bindings": bindings,
            "current_holder": holder_ref
                              or bindings["buyer_mandate_ref"],
            "transfers": [],
            "prev_hash": GENESIS,
            "registered_at": now_iso(),
            "scope": SCOPE_LABEL,
            "seal_type": SEAL_TYPE,
        }
        pack["seal"] = self._seal(pack)
        data["packs"][pack["pack_id"]] = pack
        self._save(data)
        return dict(pack)

    def get_pack(self, args):
        pack_id = args.get("pack_id")
        if not isinstance(pack_id, str) or not pack_id:
            raise ToolError("pack_id required (string)")
        data = self._load()
        pack = data["packs"].get(pack_id)
        if pack is None:
            raise Refusal("PACK_NOT_FOUND", pack_id)
        # Bench Fix D1: never serve out-of-spec content (injected keys,
        # relabelled scope) as if it were sealed pack content.
        errs = pack_structure_errors(pack)
        if errs:
            raise Refusal(
                "PACK_INVALID",
                "pack carries unsealed/out-of-spec content, not "
                "serving: " + "; ".join(errs))
        return dict(pack)

    def _verify(self, pack):
        if not isinstance(pack, dict) or "seal" not in pack:
            return {"valid": False, "result": "INVALID",
                    "reason": "no seal"}
        errs = pack_structure_errors(pack)
        if errs:
            return {"valid": False, "result": "INVALID",
                    "reason": "out-of-spec pack structure: "
                              + "; ".join(errs)}
        try:
            expected = self._seal(pack)
        except (KeyError, TypeError) as e:
            return {"valid": False, "result": "INVALID",
                    "reason": "malformed pack: " + type(e).__name__}
        if not hmac.compare_digest(expected, str(pack["seal"])):
            return {"valid": False, "result": "INVALID",
                    "reason": "seal mismatch (bound field, holder, "
                              "or transfer chain altered)"}
        # Chain audit: genesis + transfer seq/prev_seal linkage shape.
        if pack.get("prev_hash") != GENESIS:
            return {"valid": False, "result": "INVALID",
                    "reason": "chain genesis broken"}
        prev_holder = None
        for i, t in enumerate(pack.get("transfers", [])):
            if t.get("seq") != i + 1:
                return {"valid": False, "result": "INVALID",
                        "reason": "transfer chain out of order"}
            if prev_holder is not None and \
                    t.get("from_holder") != prev_holder:
                return {"valid": False, "result": "INVALID",
                        "reason": "transfer chain holder linkage broken"}
            if not t.get("prev_seal"):
                return {"valid": False, "result": "INVALID",
                        "reason": "transfer missing prev_seal"}
            prev_holder = t.get("to_holder")
        if prev_holder is not None and \
                prev_holder != pack.get("current_holder"):
            return {"valid": False, "result": "INVALID",
                    "reason": "current_holder != last transfer target"}
        return {"valid": True, "result": "VALID",
                "pack_id": pack.get("pack_id"),
                "serial": pack.get("bindings", {}).get("serial"),
                "current_holder": pack.get("current_holder"),
                "transfers": len(pack.get("transfers", [])),
                "scope": SCOPE_LABEL, "seal_type": SEAL_TYPE}

    def verify_pack(self, args):
        if "pack" in args and args.get("pack") is not None:
            if not isinstance(args["pack"], dict):
                raise ToolError("pack must be an object")
            return self._verify(args["pack"])
        try:
            pack = self.get_pack(args)
        except Refusal as r:
            # Stored pack is structurally out of spec: that is an
            # INVALID verdict, not a transport error (PACK_NOT_FOUND
            # and other refusals still propagate).
            if r.reason == "PACK_INVALID":
                return {"valid": False, "result": "INVALID",
                        "reason": r.detail or "out-of-spec pack"}
            raise
        return self._verify(pack)

    def transfer_pack(self, args):
        pack_id = args.get("pack_id")
        new_holder = args.get("new_holder_ref")
        if not isinstance(pack_id, str) or not pack_id \
                or not isinstance(new_holder, str) or not new_holder:
            raise ToolError(
                "pack_id and new_holder_ref required (strings)")
        for k in ("transfer_ref", "transferred_at"):
            if args.get(k) is not None \
                    and not isinstance(args[k], str):
                raise ToolError("field " + k + " must be a string")
        data = self._load()
        pack = data["packs"].get(pack_id)
        if pack is None:
            raise Refusal("PACK_NOT_FOUND", pack_id)
        check = self._verify(pack)
        if not check["valid"]:
            raise Refusal("PACK_INVALID",
                          "refusing transfer: " + check["reason"])
        record = {
            "seq": len(pack["transfers"]) + 1,
            "from_holder": pack["current_holder"],
            "to_holder": new_holder,
            "transfer_ref": args.get("transfer_ref") or "",
            "transferred_at": args.get("transferred_at") or now_iso(),
            "prev_seal": pack["seal"],
        }
        pack["transfers"].append(record)
        pack["current_holder"] = new_holder
        pack["seal"] = self._seal(pack)
        data["packs"][pack_id] = pack
        self._save(data)
        return dict(pack)

    def claim_check(self, args):
        serial = args.get("serial")
        if not isinstance(serial, str) or not serial:
            raise ToolError("serial required (string)")
        if args.get("pack_id") is not None \
                and not isinstance(args["pack_id"], str):
            raise ToolError("field pack_id must be a string")
        data = self._load()
        pack = None
        if args.get("pack_id"):
            cand = data["packs"].get(args["pack_id"])
            if cand and cand["bindings"]["serial"] == serial:
                pack = cand
        if pack is None:
            for p in data["packs"].values():
                if p["bindings"]["serial"] == serial:
                    pack = p
                    break
        if pack is None:
            return {"exists": False, "valid": False,
                    "transferable": False, "serial": serial,
                    "pack_id": None, "scope": SCOPE_LABEL}
        check = self._verify(pack)
        return {"exists": True, "valid": check["valid"],
                "transferable": bool(check["valid"]),
                "serial": serial, "pack_id": pack["pack_id"],
                "current_holder": pack["current_holder"],
                "transfers": len(pack["transfers"]),
                "scope": SCOPE_LABEL, "seal_type": SEAL_TYPE}
