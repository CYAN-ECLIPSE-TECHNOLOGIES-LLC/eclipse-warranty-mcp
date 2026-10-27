#!/usr/bin/env python3
# Eclipse Warranty MCP server — stdio JSON-RPC, Python stdlib only.
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
"""Five tools, closed surface (SPEC §5):

  register_warranty  seal serial+mandate+receipt into a claim pack
  get_pack           retrieve pack + bindings
  verify_pack        recompute seal + chain; tamper = INVALID
  transfer_pack      chained re-bind to a new holder (no account)
  claim_check        does a valid transferable pack exist for serial?

Unknown tool name -> NO_SUCH_TOOL refusal. State: env
ECLIPSE_WARRANTY_DATA_DIR else ./data; demo key: env
ECLIPSE_WARRANTY_KEY_FILE else ./keys/demo.key (gitignored).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DESCRIPTOR, PRODUCT_NAME, TOOL_VERSION  # noqa: E402
from errors import Refusal, ToolError  # noqa: E402
from warranty import WarrantyStore  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("ECLIPSE_WARRANTY_DATA_DIR",
                          os.path.join(HERE, "data"))
KEY_FILE = os.environ.get("ECLIPSE_WARRANTY_KEY_FILE",
                          os.path.join(HERE, "keys", "demo.key"))
STORE = WarrantyStore(DATA_DIR, KEY_FILE)
SERVER_NAME = "io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-warranty-mcp"

_STR = {"type": "string"}


def _obj(props, required):
    return {"type": "object", "properties": props,
            "required": required, "additionalProperties": False}


TOOLS = {
    "register_warranty": {
        "fn": STORE.register_warranty,
        "schema": _obj({
            "serial": _STR, "product_ref": _STR,
            "buyer_mandate_ref": _STR, "retailer_receipt_ref": _STR,
            "purchase_ts": _STR, "holder_ref": _STR},
            ["serial", "product_ref", "buyer_mandate_ref",
             "retailer_receipt_ref", "purchase_ts"]),
        "description": "Register a warranty claim pack: binds serial, "
                       "product, buyer mandate ref, retailer receipt "
                       "ref, and purchase timestamp into one sealed, "
                       "transferable witness pack (LOCAL/fixture)."},
    "get_pack": {
        "fn": STORE.get_pack,
        "schema": _obj({"pack_id": _STR}, ["pack_id"]),
        "description": "Retrieve a claim pack by pack_id, showing all "
                       "bindings, current holder, and transfer chain."},
    "verify_pack": {
        "fn": STORE.verify_pack,
        "schema": _obj({"pack_id": _STR,
                        "pack": {"type": "object"}}, []),
        "description": "Verify a pack by recomputing its seal and "
                       "transfer-chain linkage. No account or original "
                       "holder needed. Tamper with any bound field "
                       "returns INVALID."},
    "transfer_pack": {
        "fn": STORE.transfer_pack,
        "schema": _obj({
            "pack_id": _STR, "new_holder_ref": _STR,
            "transfer_ref": _STR, "transferred_at": _STR},
            ["pack_id", "new_holder_ref"]),
        "description": "Transfer a pack to a new holder with a chained "
                       "transfer record and re-seal. Validity derives "
                       "from serial + purchase proof chain, not any "
                       "account identity."},
    "claim_check": {
        "fn": STORE.claim_check,
        "schema": _obj({"serial": _STR, "pack_id": _STR}, ["serial"]),
        "description": "Given a serial (and optionally a pack_id), "
                       "answer whether a valid transferable claim pack "
                       "exists for it."},
}


def dispatch(name, args):
    if name not in TOOLS:
        raise Refusal(
            "NO_SUCH_TOOL",
            f"{name!r} is not a tool here. This surface witnesses "
            "warranty registrations only; it adjudicates nothing.")
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    return TOOLS[name]["fn"](args)


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": TOOL_VERSION,
                           "description": DESCRIPTOR}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": t["description"],
             "inputSchema": t["schema"]}
            for n, t in TOOLS.items()]}}
    if method == "tools/call":
        params = req.get("params", {})
        try:
            result = dispatch(params.get("name"),
                              params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "isError": False,
                "content": [{"type": "text",
                             "text": json.dumps(result, sort_keys=True)}]}}
        except Refusal as r:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps(
                    {"refusal": r.reason, "detail": r.detail},
                    sort_keys=True)}]}}
        except ToolError as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps(
                    {"error": str(e)}, sort_keys=True)}]}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601,
                      "message": f"method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
