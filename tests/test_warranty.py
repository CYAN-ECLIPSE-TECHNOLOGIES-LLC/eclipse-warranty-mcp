# Eclipse Warranty tests — SPEC §8 battery (builder suite; bench re-runs).
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from errors import Refusal, ToolError  # noqa: E402
from warranty import BOUND_FIELDS, WarrantyStore  # noqa: E402

FIXTURE = {
    "serial": "SN-FIXTURE-0001",
    "product_ref": "fixture:widget-pro-x1",
    "buyer_mandate_ref": "mandate:fixture-buyer-001",
    "retailer_receipt_ref": "receipt:fixture-retailer-8842",
    "purchase_ts": "2026-10-20T14:03:00Z",
    "holder_ref": "holder:alice",
}


class TestWarranty(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        self.key = os.path.join(self.tmp.name, "keys", "demo.key")
        self.store = WarrantyStore(self.data_dir, self.key)
        self.pack = self.store.register_warranty(dict(FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def reload(self):
        return WarrantyStore(self.data_dir, self.key)

    def tamper_stored(self, mutate):
        path = os.path.join(self.data_dir, "packs.json")
        with open(path) as f:
            data = json.load(f)
        mutate(data["packs"][self.pack["pack_id"]])
        with open(path, "w") as f:
            json.dump(data, f)
        return self.reload().verify_pack({"pack_id": self.pack["pack_id"]})

    # seal verify ------------------------------------------------------
    def test_seal_verify_valid(self):
        out = self.store.verify_pack({"pack_id": self.pack["pack_id"]})
        self.assertTrue(out["valid"])
        self.assertEqual(out["result"], "VALID")
        self.assertEqual(self.pack["prev_hash"], "GENESIS")
        self.assertTrue(self.pack["seal"])

    def test_verify_supplied_pack_object(self):
        out = self.store.verify_pack({"pack": copy.deepcopy(self.pack)})
        self.assertTrue(out["valid"])

    # tamper detection per bound field ---------------------------------
    def test_tamper_each_bound_field_invalid(self):
        for field in BOUND_FIELDS:
            with self.subTest(field=field):
                def mutate(p, f=field):
                    p["bindings"][f] = p["bindings"][f] + "-TAMPERED"
                out = self.tamper_stored(mutate)
                self.assertFalse(out["valid"])
                self.assertEqual(out["result"], "INVALID")

    def test_tamper_holder_invalid(self):
        out = self.tamper_stored(
            lambda p: p.update({"current_holder": "holder:mallory"}))
        self.assertFalse(out["valid"])

    def test_tamper_seal_invalid(self):
        out = self.store.verify_pack(
            {"pack": dict(copy.deepcopy(self.pack), seal="0" * 64)})
        self.assertFalse(out["valid"])

    # transfer ---------------------------------------------------------
    def test_transfer_preserves_validity(self):
        moved = self.store.transfer_pack({
            "pack_id": self.pack["pack_id"],
            "new_holder_ref": "holder:bob",
            "transfer_ref": "resale:fixture-001",
            "transferred_at": "2026-10-25T09:00:00Z"})
        self.assertEqual(moved["current_holder"], "holder:bob")
        # Original bindings untouched by transfer.
        for f in BOUND_FIELDS:
            self.assertEqual(moved["bindings"][f], FIXTURE[f])
        # Verifies fresh from a reloaded store — no original holder,
        # no account, nothing but serial + purchase-proof chain.
        out = self.reload().verify_pack({"pack_id": self.pack["pack_id"]})
        self.assertTrue(out["valid"])
        self.assertEqual(out["current_holder"], "holder:bob")

    def test_transfer_chain_audit(self):
        genesis_seal = self.pack["seal"]
        p1 = self.store.transfer_pack({
            "pack_id": self.pack["pack_id"], "new_holder_ref": "holder:bob",
            "transferred_at": "2026-10-25T09:00:00Z"})
        p2 = self.store.transfer_pack({
            "pack_id": self.pack["pack_id"],
            "new_holder_ref": "holder:carol",
            "transferred_at": "2026-10-26T09:00:00Z"})
        chain = p2["transfers"]
        self.assertEqual(len(chain), 2)
        self.assertEqual([t["seq"] for t in chain], [1, 2])
        self.assertEqual(chain[0]["prev_seal"], genesis_seal)
        self.assertEqual(chain[1]["prev_seal"], p1["seal"])
        self.assertEqual(chain[0]["from_holder"], "holder:alice")
        self.assertEqual(chain[0]["to_holder"], "holder:bob")
        self.assertEqual(chain[1]["from_holder"], "holder:bob")
        self.assertEqual(chain[1]["to_holder"], "holder:carol")
        self.assertTrue(self.store.verify_pack(
            {"pack_id": self.pack["pack_id"]})["valid"])

    def test_tampered_transfer_record_invalid(self):
        self.store.transfer_pack({
            "pack_id": self.pack["pack_id"], "new_holder_ref": "holder:bob"})
        out = self.tamper_stored(
            lambda p: p["transfers"][0].update({"to_holder": "holder:eve"}))
        self.assertFalse(out["valid"])

    def test_invalid_pack_cannot_transfer(self):
        path = os.path.join(self.data_dir, "packs.json")
        with open(path) as f:
            data = json.load(f)
        data["packs"][self.pack["pack_id"]]["bindings"]["serial"] = "X"
        with open(path, "w") as f:
            json.dump(data, f)
        with self.assertRaises(Refusal) as ctx:
            self.reload().transfer_pack({
                "pack_id": self.pack["pack_id"],
                "new_holder_ref": "holder:bob"})
        self.assertEqual(ctx.exception.reason, "PACK_INVALID")

    # claim_check --------------------------------------------------------
    def test_claim_check_registered_serial(self):
        out = self.store.claim_check({"serial": FIXTURE["serial"]})
        self.assertTrue(out["exists"])
        self.assertTrue(out["valid"])
        self.assertTrue(out["transferable"])

    def test_claim_check_after_transfer(self):
        self.store.transfer_pack({
            "pack_id": self.pack["pack_id"], "new_holder_ref": "holder:bob"})
        out = self.store.claim_check(
            {"serial": FIXTURE["serial"], "pack_id": self.pack["pack_id"]})
        self.assertTrue(out["exists"])
        self.assertTrue(out["transferable"])
        self.assertEqual(out["current_holder"], "holder:bob")

    def test_unregistered_serial_no_pack(self):
        out = self.store.claim_check({"serial": "SN-NEVER-REGISTERED"})
        self.assertFalse(out["exists"])
        self.assertFalse(out["valid"])
        self.assertFalse(out["transferable"])
        self.assertIsNone(out["pack_id"])

    # registration guards --------------------------------------------------
    def test_duplicate_serial_refused(self):
        with self.assertRaises(Refusal) as ctx:
            self.store.register_warranty(dict(FIXTURE))
        self.assertEqual(ctx.exception.reason, "SERIAL_ALREADY_REGISTERED")

    def test_get_pack_roundtrip(self):
        got = self.store.get_pack({"pack_id": self.pack["pack_id"]})
        self.assertEqual(got["bindings"]["serial"], FIXTURE["serial"])
        self.assertEqual(got["scope"], "LOCAL/fixture")

    # Bench Fix D1 regressions (Verity P2-OBS repros) -------------------
    def test_d1_injected_bindings_key_supplied_invalid(self):
        evil = copy.deepcopy(self.pack)
        evil["bindings"]["injected_coverage"] = "lifetime-full"
        out = self.store.verify_pack({"pack": evil})
        self.assertFalse(out["valid"])
        self.assertEqual(out["result"], "INVALID")

    def test_d1_injected_bindings_key_stored_invalid_not_served(self):
        out = self.tamper_stored(
            lambda p: p["bindings"].update(
                {"injected_coverage": "lifetime-full"}))
        self.assertFalse(out["valid"])
        self.assertEqual(out["result"], "INVALID")
        with self.assertRaises(Refusal) as ctx:
            self.reload().get_pack({"pack_id": self.pack["pack_id"]})
        self.assertEqual(ctx.exception.reason, "PACK_INVALID")

    def test_d1_extra_top_level_key_supplied_invalid(self):
        evil = copy.deepcopy(self.pack)
        evil["injected_top_level"] = "lifetime-full"
        out = self.store.verify_pack({"pack": evil})
        self.assertFalse(out["valid"])

    def test_d1_extra_transfer_key_supplied_invalid(self):
        self.store.transfer_pack({
            "pack_id": self.pack["pack_id"], "new_holder_ref": "holder:bob"})
        evil = copy.deepcopy(
            self.store.get_pack({"pack_id": self.pack["pack_id"]}))
        evil["transfers"][0]["injected_coverage"] = "lifetime-full"
        out = self.store.verify_pack({"pack": evil})
        self.assertFalse(out["valid"])

    def test_d1_scope_relabel_supplied_invalid(self):
        evil = copy.deepcopy(self.pack)
        evil["scope"] = "LIVE/production"
        out = self.store.verify_pack({"pack": evil})
        self.assertFalse(out["valid"])
        self.assertEqual(out["result"], "INVALID")

    def test_d1_scope_relabel_stored_invalid_not_served(self):
        out = self.tamper_stored(
            lambda p: p.update({"scope": "LIVE/production"}))
        self.assertFalse(out["valid"])
        with self.assertRaises(Refusal) as ctx:
            self.reload().get_pack({"pack_id": self.pack["pack_id"]})
        self.assertEqual(ctx.exception.reason, "PACK_INVALID")

    def test_d1_registered_at_tamper_invalid_full_seal(self):
        # registered_at was unsealed in v0.1.0; the v0.1.1 full-content
        # seal covers it.
        evil = copy.deepcopy(self.pack)
        evil["registered_at"] = "1999-01-01T00:00:00Z"
        out = self.store.verify_pack({"pack": evil})
        self.assertFalse(out["valid"])

    # Bench Fix D2 regressions (store level; wire level below) ---------
    def test_d2_int_purchase_ts_rejected_no_coercion(self):
        args = dict(FIXTURE, serial="SN-D2-INT-TS", purchase_ts=20260901)
        with self.assertRaises(ToolError):
            self.store.register_warranty(args)
        out = self.store.claim_check({"serial": "SN-D2-INT-TS"})
        self.assertFalse(out["exists"])

    def test_d2_list_serial_rejected_no_coercion(self):
        args = dict(FIXTURE, serial=["SN-LIST"])
        with self.assertRaises(ToolError):
            self.store.register_warranty(args)


WIRE_BASE = {
    "serial": "SN-WIRE-0001",
    "product_ref": "wire:widget",
    "buyer_mandate_ref": "mandate:wire-buyer",
    "retailer_receipt_ref": "receipt:wire-retailer",
    "purchase_ts": "2026-09-01T10:00:00Z",
    "holder_ref": "holder:alice",
}
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class WireClient:
    """Minimal stdio JSON-RPC client (replicates the bench route)."""

    def __init__(self, tmp):
        env = dict(os.environ)
        env["ECLIPSE_WARRANTY_DATA_DIR"] = os.path.join(tmp, "data")
        env["ECLIPSE_WARRANTY_KEY_FILE"] = os.path.join(
            tmp, "keys", "demo.key")
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(REPO_ROOT, "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=REPO_ROOT, env=env)
        self._id = 0
        self.rpc("initialize", {})

    def rpc(self, method, params):
        self._id += 1
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": method,
             "params": params}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, tool, args):
        r = self.rpc("tools/call", {"name": tool, "arguments": args})
        body = json.loads(r["result"]["content"][0]["text"])
        return r["result"].get("isError", False), body

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class TestBenchReprosWire(unittest.TestCase):
    """Bench P2-OBS / P4-OBS repros over the wire, post-fix."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = WireClient(self.tmp.name)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_d2_int_purchase_ts_rejected(self):
        err, body = self.client.call(
            "register_warranty", dict(WIRE_BASE, purchase_ts=20260901))
        self.assertTrue(err, body)
        err, cc = self.client.call(
            "claim_check", {"serial": WIRE_BASE["serial"]})
        self.assertFalse(err)
        self.assertFalse(cc["exists"])

    def test_d2_list_serial_rejected(self):
        err, body = self.client.call(
            "register_warranty", dict(WIRE_BASE, serial=["SN-LIST"]))
        self.assertTrue(err, body)

    def test_d2_extra_fields_rejected(self):
        err, body = self.client.call(
            "register_warranty",
            dict(WIRE_BASE, admin=True, coverage="full"))
        self.assertTrue(err, body)
        self.assertIn("additionalProperties", body.get("error", ""))

    def test_d2_wrong_type_on_other_tools_rejected(self):
        err, _ = self.client.call("get_pack", {"pack_id": 123})
        self.assertTrue(err)
        err, _ = self.client.call("claim_check", {"serial": 42})
        self.assertTrue(err)
        err, _ = self.client.call(
            "verify_pack", {"pack": "not-an-object"})
        self.assertTrue(err)

    def test_d1_wire_injected_and_relabelled_pack_invalid(self):
        err, pack = self.client.call("register_warranty", dict(WIRE_BASE))
        self.assertFalse(err, pack)
        evil = copy.deepcopy(pack)
        evil["bindings"]["injected_coverage"] = "lifetime-full"
        err, v = self.client.call("verify_pack", {"pack": evil})
        self.assertFalse(err)
        self.assertEqual(v["result"], "INVALID")
        evil2 = copy.deepcopy(pack)
        evil2["scope"] = "LIVE/production"
        err, v2 = self.client.call("verify_pack", {"pack": evil2})
        self.assertFalse(err)
        self.assertEqual(v2["result"], "INVALID")
        # Control: the untouched pack still verifies VALID.
        err, v3 = self.client.call(
            "verify_pack", {"pack_id": pack["pack_id"]})
        self.assertFalse(err)
        self.assertEqual(v3["result"], "VALID")


if __name__ == "__main__":
    unittest.main()
