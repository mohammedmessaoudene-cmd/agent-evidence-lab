"""Run one ordinary product update using the pinned ServiceNow client on loopback."""
import asyncio
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import socket
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
OUTPUT = Path("/tmp/dot-p03-receipt.json")
URL = "http://127.0.0.1:8005"
READ = "retrieve_installed_products"
WRITE = "update_installed_product_details"
FIELDS = ("name", "description", "inputSchema", "outputSchema")
EXPECTED_CATALOG = "d95260ecfd3610282483ebbfb2203ff1f98271a8cc38870ce2978af086d48300"
BEFORE = {"installed_product_id": 40, "location_id": 817, "status": "in_use"}
AFTER = {"installed_product_id": 40, "location_id": 692, "status": "in_use"}


def require(condition, stage):
    if not condition:
        raise ValueError(stage)


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save(report):
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)


def checkpoint(report, stage):
    report["stage"] = stage
    save(report)


def public_client():
    spec = importlib.util.spec_from_file_location("case_mcp_client", HERE / "mcp_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def product(result, multiple):
    require(result.get("success") is True and not result.get("error"), "tool transport")
    output = result["result"]
    require(output.get("isError") is False, "tool outcome")
    part, = output["content"]
    require(part["type"] == "text", "tool content")
    value = json.loads(part["text"])
    if multiple:
        require(isinstance(value, list) and len(value) == 1, "one product required")
        value = value[0]
    require(isinstance(value, dict), "product record")
    row = {field: value[field] for field in BEFORE}
    require(type(row["installed_product_id"]) is int and type(row["location_id"]) is int
            and row["installed_product_id"] == 40 and row["status"] in ("in_use", "in_stock", "repair", "retired"),
            "product values")
    return row


def catalog_record(tools):
    by_name = {}
    for tool in tools:
        name = tool["name"]
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9_]{1,120}", name) and name not in by_name,
                "tool name")
        by_name[name] = {key: tool[key] for key in FIELDS}
    return {"count": len(tools), "four_fields_by_name_sha256": digest(by_name),
            "ordered_four_field_record_sha256": [digest(by_name[tool["name"]]) for tool in tools],
            "full_ordered_tools_sha256": digest(tools),
            "ordered_tool_names_and_full_record_sha256": [[tool["name"], digest(tool)] for tool in tools]}


def sql_count(config, db, context):
    require(config["expected_value"] == 1 and config["comparison_type"] == "equals", "case verifier")
    payload = json.dumps({"database_id": db, "query": config["query"]}).encode()
    request = Request(URL + "/api/sql-runner", data=payload,
                      headers={"Content-Type": "application/json", "x-database-id": db, **context})
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        result = json.load(response)
    require(result["success"] is True and result["row_count"] == 1, "SQL status")
    only_row, = result["data"]
    count, = only_row.values()
    require(type(count) is int and count in (0, 1), "SQL count")
    return count


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
    module = public_client()
    task = json.loads((HERE / "task.json").read_bytes())
    server, = task["gym_servers_config"]
    context = server["context"]
    verifier, = (v for v in task["verifiers"] if v["name"] == "Verify Updated Installed Product")
    checkpoint(report, "seed")
    db = module.create_database_from_file(URL, str(HERE / "seed.sql"))
    require(isinstance(db, str) and re.fullmatch(r"db_[0-9]+_[a-z0-9]{9}", db), "database identity")
    report["database_id"] = db
    writer = module.MCPClient(URL, database_id=db, context=context)
    checkpoint(report, "catalog")
    require(await writer.connect(), "writer connection")
    report["served_catalog"] = catalog_record(await writer.list_tools())
    save(report)
    require(report["served_catalog"]["count"] == 89
            and report["served_catalog"]["four_fields_by_name_sha256"] == EXPECTED_CATALOG, "served catalog")
    checkpoint(report, "before")
    report["before"] = product(await writer.call_tool(READ, {"installed_product_id": 40}), True)
    save(report)
    require(report["before"] == BEFORE, "initial state")

    report["write_requests_started"] = 1
    report["write_outcome"] = "OUTCOME_PENDING"
    checkpoint(report, "write")
    try:
        reply = await writer.call_tool(WRITE, AFTER.copy())
        report["write_reply"] = product(reply, False)
        report["write_outcome"] = "ACKNOWLEDGED"
    except Exception as error:
        report["write_error_type"] = type(error).__name__
    save(report)

    checkpoint(report, "second_client")
    reader = module.MCPClient(URL, database_id=db, context=context)
    require(await reader.connect(), "reader connection")
    report["second_client_initialized"] = True
    report["after"] = product(await reader.call_tool(READ, {"installed_product_id": 40}), True)
    checkpoint(report, "sql")
    report["official_verifier_count"] = sql_count(verifier["validation_config"], db, context)
    save(report)
    require(report["after"] == AFTER and report["official_verifier_count"] == 1, "persistent state")
    require(report.get("write_reply") == AFTER, "write result")
    report["outcome"] = "PERSISTED_PRODUCT_40_OBSERVED"
    checkpoint(report, "complete")


def main():
    logging.disable(logging.CRITICAL)
    report = {"outcome": "INCOMPLETE", "stage": "start", "write_requests_started": 0,
              "write_outcome": "NOT_RUN", "second_client_initialized": False, "started_unix": int(time.time())}
    try:
        asyncio.run(exercise(report))
    except Exception as error:
        # Upstream error text can contain fixture context or records.
        report["error_type"] = type(error).__name__
    finally:
        report["finished_unix"] = int(time.time())
        save(report)
    return 0 if report["outcome"] == "PERSISTED_PRODUCT_40_OBSERVED" else 1


if __name__ == "__main__":
    sys.exit(main())
