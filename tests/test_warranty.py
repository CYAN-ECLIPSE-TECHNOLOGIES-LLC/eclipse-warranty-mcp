# Eclipse Warranty tests — SPEC §8 battery (builder suite; bench re-runs).
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from errors import Refusal  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
