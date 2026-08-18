#!/usr/bin/env python3
"""Small local persistence layer for the WorkTex layered-Skill demo.

It deliberately uses SQLite and the existing deterministic scorer so the demo
can show a durable run log before a hosted API or CRM connector is added.
It never crawls a website or sends an outbound message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sales_intel_mvp import deduplicate, load_records, score_lead


STAGES = [
    ("lead-intake", "线索处理", "收到线索"),
    ("company-verification", "线索处理", "核验公司"),
    ("buyer-fit", "线索处理", "判断是否适合"),
    ("signal-analysis", "线索处理", "分析采购信号"),
    ("product-match", "商务准备", "匹配产品"),
    ("contact-draft", "商务准备", "生成联系草稿"),
    ("quote-draft", "商务准备", "整理报价字段"),
    ("crm-followup", "客户跟进", "写入跟进任务"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lead_id(record: dict[str, Any]) -> str:
    source = str(record.get("domain") or record.get("company") or "").strip().lower()
    return "WT-" + hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS leads (
          id TEXT PRIMARY KEY,
          company TEXT NOT NULL,
          domain TEXT,
          country TEXT,
          buyer_type TEXT,
          product_fit TEXT,
          score INTEGER,
          grade TEXT,
          human_label TEXT,
          review_status TEXT NOT NULL DEFAULT '待人工核验',
          raw_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
          signal TEXT,
          source_type TEXT,
          url TEXT,
          observed_on TEXT,
          excerpt TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
          skill_id TEXT NOT NULL,
          module TEXT NOT NULL,
          label TEXT NOT NULL,
          status TEXT NOT NULL,
          output_json TEXT NOT NULL,
          run_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id TEXT,
          event_type TEXT NOT NULL,
          message TEXT NOT NULL,
          event_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def stage_status(result: Any, stage_id: str) -> tuple[str, str]:
    if result.grade == "C" or result.human_label.startswith("C_"):
        if stage_id in {"buyer-fit", "product-match", "contact-draft", "quote-draft", "crm-followup"}:
            return "已拦截", "命中排除或安全规则，流程停止。"
        return "已完成", "基础线索处理已完成。"
    if stage_id in {"contact-draft", "quote-draft"}:
        return "等待人工确认", "已生成建议，但外发和报价必须由人工确认。"
    if stage_id == "crm-followup":
        return ("已生成" if result.grade == "A" else "需要补资料"), result.next_action
    return "已完成", result.next_action


def ingest(conn: sqlite3.Connection, input_path: Path) -> dict[str, Any]:
    raw = load_records(input_path)
    records, duplicate_notes = deduplicate(raw)
    stamp = now()
    for record in records:
        result = score_lead(record)
        lid = lead_id(record)
        conn.execute(
            """INSERT INTO leads(id,company,domain,country,buyer_type,product_fit,score,grade,human_label,review_status,raw_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET company=excluded.company,domain=excluded.domain,country=excluded.country,
               buyer_type=excluded.buyer_type,product_fit=excluded.product_fit,score=excluded.score,grade=excluded.grade,
               human_label=excluded.human_label,raw_json=excluded.raw_json,updated_at=excluded.updated_at""",
            (lid, result.company, result.domain, result.country, result.buyer_type, result.product_fit, result.score, result.grade, result.human_label, "待人工核验", json.dumps(record, ensure_ascii=False), stamp, stamp),
        )
        conn.execute("DELETE FROM evidence WHERE lead_id=?", (lid,))
        conn.execute("DELETE FROM skill_runs WHERE lead_id=?", (lid,))
        for item in record.get("evidence", []):
            conn.execute("INSERT INTO evidence(lead_id,signal,source_type,url,observed_on,excerpt) VALUES(?,?,?,?,?,?)", (lid, item.get("signal"), item.get("source_type"), item.get("url"), item.get("observed_on"), item.get("excerpt")))
        for skill_id, module, label in STAGES:
            status, message = stage_status(result, skill_id)
            output = {"status": status, "message": message, "grade": result.grade, "score": result.score, "requires_human": status == "等待人工确认"}
            conn.execute("INSERT INTO skill_runs(lead_id,skill_id,module,label,status,output_json,run_at) VALUES(?,?,?,?,?,?,?)", (lid, skill_id, module, label, status, json.dumps(output, ensure_ascii=False), stamp))
        conn.execute("INSERT INTO events(lead_id,event_type,message,event_json,created_at) VALUES(?,?,?,?,?)", (lid, "AUTOMATION_RUN", "分层 Skill 已完成一次处理", json.dumps({"grade": result.grade, "score": result.score, "hard_gates": result.hard_gates_failed}, ensure_ascii=False), stamp))
    conn.commit()
    return {"input_records": len(raw), "unique_records": len(records), "duplicates_merged": len(duplicate_notes), "db": "持久化完成"}


def export_report(conn: sqlite3.Connection, output_path: Path) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM leads ORDER BY score DESC, company").fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        lead = dict(row)
        lead["evidence"] = [dict(item) for item in conn.execute("SELECT signal,source_type,url,observed_on,excerpt FROM evidence WHERE lead_id=?", (lead["id"],)).fetchall()]
        lead["skill_runs"] = []
        for item in conn.execute("SELECT skill_id,module,label,status,output_json,run_at FROM skill_runs WHERE lead_id=? ORDER BY id", (lead["id"],)).fetchall():
            skill = dict(item)
            skill["output"] = json.loads(skill.pop("output_json"))
            lead["skill_runs"].append(skill)
        result.append(lead)
    output = {"generated_at": now(), "count": len(result), "leads": result}
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"count": len(result), "json_out": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist and replay the WorkTex layered-Skill demo")
    parser.add_argument("command", choices=["init", "ingest", "export"])
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--db", type=Path, default=Path("worktex_pipeline.db"))
    parser.add_argument("--json-out", type=Path, default=Path("worktex_pipeline_export.json"))
    args = parser.parse_args()
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        if args.command == "init":
            print(json.dumps({"db": str(args.db), "status": "initialized"}, ensure_ascii=False))
        elif args.command == "ingest":
            if not args.input:
                parser.error("ingest requires an input JSON file")
            print(json.dumps(ingest(conn, args.input), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(export_report(conn, args.json_out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
