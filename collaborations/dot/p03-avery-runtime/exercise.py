"""One case and its requested interaction, observed by the official SQL verifiers."""
import asyncio
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import socket
from urllib.request import ProxyHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
OUTPUT = Path("/tmp/dot-p03-receipt.json")
URL = "http://127.0.0.1:8005"
CASE = {"account_id": 44, "contact_id": 101, "product_id": 140, "installed_product_id": 243,
        "channel": "social", "priority": "moderate", "state": "new",
        "short_description": "Product: Palo Alto Networks PA-3220 Variant 8, Issue: unusually high operating noise."}
INTERACTION = {"account_id": 44, "contact_id": 101, "channel": "social", "status": "handled"}
TOOLS = {"create_new_case": "05f4d42c12ce6f2de0cf0b76cdda55ebf4474d188e43af47819d412291d9779e",
         "register_new_interaction": "5edb523b4289c990ea2049ee4b509df6aea89c62df4ade5d564d3a44d766bc08"}


def require(value):
    if not value:
        raise ValueError("unconfirmed observation")


def checkpoint(report, stage):
    report["stage"] = stage
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)


def sql_counts(task, database_id):
    counts = []
    for query in task["queries"]:
        payload = json.dumps({"database_id": database_id, "query": query}).encode()
        headers = {"Content-Type": "application/json", "x-database-id": database_id, **task["context"]}
        request = Request(URL + "/api/sql-runner", data=payload, headers=headers)
        with build_opener(ProxyHandler({})).open(request, timeout=12) as response:
            result = json.load(response)
        require(result.get("success") is True and result["row_count"] == 1)
        row, = result["data"]
        count, = row.values()
        require(type(count) is int and 0 <= count <= 10000)
        counts.append(count)
    return counts


def ack(response, expected):
    require(response.get("success") is True and not response.get("error"))
    result = response["result"]
    require(result.get("isError") is False)
    part, = result["content"]
    require(part["type"] == "text")
    record = json.loads(part["text"])
    require(isinstance(record, dict) and all(type(record.get(k)) is type(v) and record[k] == v
                                            for k, v in expected.items()))
    return record


async def exercise(report):
    checkpoint(report, "startup")
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", 8005), timeout=0.5):
                break
        except OSError:
            await asyncio.sleep(0.5)
    else:
        raise TimeoutError("startup")
    task = json.loads((HERE / "task.json").read_bytes())
    require(set(task["context"]) == {"x-user-email"} and len(task["queries"]) == 2)
    spec = importlib.util.spec_from_file_location("official_client", HERE / "mcp_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checkpoint(report, "seed")
    db = module.create_database_from_file(URL, str(HERE / "seed.sql"))
    require(isinstance(db, str) and re.fullmatch(r"db_[0-9]{13}_[a-z0-9]{9}", db))
    report["database_id_sha256"] = hashlib.sha256(db.encode("ascii")).hexdigest()
    writer = module.MCPClient(URL, database_id=db, context=task["context"])
    require(await writer.connect())
    catalog = await writer.list_tools()
    for name, digest in TOOLS.items():
        tool, = [item for item in catalog if item["name"] == name]
        fields = {k: tool[k] for k in ("name", "description", "inputSchema", "outputSchema")}
        data = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        require(hashlib.sha256(data).hexdigest() == digest)
    report["served_schemas_match"] = True
    checkpoint(report, "before")
    report["before"] = sql_counts(task, db)
    require(report["before"] == [0, 0])
    report["case_write"] = "OUTCOME_PENDING"
    checkpoint(report, "create_case")
    try:
        row = ack(await writer.call_tool("create_new_case", CASE.copy()), CASE)
        require(type(row["case_id"]) is int and row["case_id"] == 1233)
        require(row["number"] == "CS-0001233")
        report["case_id"] = row["case_id"]
        report["case_number"] = row["number"]
        report["case_write"] = "ACKNOWLEDGED"
    finally:
        checkpoint(report, "read_case")
        report["after_case"] = sql_counts(task, db)
        checkpoint(report, "read_case")
    require(report["after_case"] == [1, 0])
    payload = dict(INTERACTION, case_id=report["case_id"])
    report["interaction_write"] = "OUTCOME_PENDING"
    checkpoint(report, "register_interaction")
    try:
        item = ack(await writer.call_tool("register_new_interaction", payload), payload)
        require(type(item["interaction_id"]) is int and 0 < item["interaction_id"] <= 2**31-1)
        report["interaction_id"] = item["interaction_id"]
        report["interaction_write"] = "ACKNOWLEDGED"
    finally:
        checkpoint(report, "read_interaction")
        report["after_interaction"] = sql_counts(task, db)
        checkpoint(report, "read_interaction")
    require(report["after_interaction"] == [1, 1])
    checkpoint(report, "complete")


def main():
    logging.disable(logging.CRITICAL)
    report = {"stage": "start", "case_write": "NOT_RUN", "interaction_write": "NOT_RUN"}
    try:
        asyncio.run(exercise(report))
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
