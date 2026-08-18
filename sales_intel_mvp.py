#!/usr/bin/env python3
"""A local, deterministic MVP for export-sales intelligence.

The MVP intentionally works on supplied evidence records. It does not crawl
websites, guess personal emails, or send outreach. This makes scoring and
review behavior reproducible before connectors are added.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


TODAY = date(2026, 8, 17)
DEFAULT_FRESHNESS_DAYS = 90
EXCLUDED_TERMS = {
    "training",
    "course",
    "agency",
    "marketing service",
    "ai company",
    "software vendor",
    "培训",
    "代理商服务",
    "广告公司",
    "ai公司",
}


@dataclass
class Evidence:
    signal: str
    source_type: str
    url: str
    observed_on: str
    excerpt: str

    @property
    def observed_date(self) -> date | None:
        try:
            return datetime.strptime(self.observed_on, "%Y-%m-%d").date()
        except ValueError:
            return None


@dataclass
class LeadResult:
    company: str
    domain: str
    country: str
    buyer_type: str
    product_fit: str
    score: int
    grade: str
    evidence_confidence: str
    verified: bool
    eligible_for_contact_review: bool
    reasons: list[str] = field(default_factory=list)
    hard_gates_failed: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    next_action: str = ""
    human_label: str = ""
    annotation_reason: str = ""
    annotation_reviewer: str = ""
    synthetic_demo: bool = False


def normalize_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/")


def normalize_company(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)
    for suffix in ("limited", "ltd", "llc", "incorporated", "inc", "公司", "有限公司"):
        value = value.replace(suffix, "")
    return value


def parse_evidence(raw: dict[str, Any]) -> Evidence:
    return Evidence(
        signal=str(raw.get("signal", "")).strip().lower(),
        source_type=str(raw.get("source_type", "")).strip().lower(),
        url=str(raw.get("url", "")).strip(),
        observed_on=str(raw.get("observed_on", "")).strip(),
        excerpt=str(raw.get("excerpt", "")).strip(),
    )


def freshness_points(evidence: Iterable[Evidence], today: date = TODAY) -> int:
    dates = [e.observed_date for e in evidence if e.observed_date]
    if not dates:
        return 0
    age = (today - max(dates)).days
    if age <= 30:
        return 10
    if age <= 60:
        return 8
    if age <= 90:
        return 5
    return 0


def evidence_confidence(evidence: list[Evidence], verified: bool) -> str:
    source_types = {e.source_type for e in evidence if e.url and e.excerpt}
    usable = [e for e in evidence if e.url and e.excerpt and e.observed_date]
    if verified and len(usable) >= 2 and len(source_types) >= 2:
        return "high"
    if len(usable) >= 1:
        return "medium"
    return "low"


def is_excluded(lead: dict[str, Any]) -> bool:
    text = " ".join(
        str(lead.get(key, "")) for key in ("company", "description", "buyer_type", "product_fit")
    ).lower()
    return any(term in text for term in EXCLUDED_TERMS)


def company_verified(lead: dict[str, Any], evidence: list[Evidence]) -> bool:
    domain = normalize_domain(str(lead.get("domain", "")))
    has_site_evidence = any(e.source_type in {"official_site", "registry", "trade_fair", "association"} and e.url for e in evidence)
    return bool(domain and has_site_evidence)


def has_current_signal(evidence: list[Evidence], today: date = TODAY) -> bool:
    return any(e.observed_date and 0 <= (today - e.observed_date).days <= DEFAULT_FRESHNESS_DAYS for e in evidence)


def contact_gate(lead: dict[str, Any]) -> tuple[bool, str]:
    """Return whether a record may enter manual contact review.

    This is deliberately stricter than merely having a public email. The MVP
    never sends; it only determines whether a human may inspect the record.
    """
    if is_excluded(lead):
        return False, "excluded business type"
    if lead.get("contact_mode") not in {"corporate_email", "official_form", "authorized_event"}:
        return False, "contact route is not an approved corporate/authorized route"
    if lead.get("suppressed"):
        return False, "suppressed or opted out"
    if lead.get("contact_review_status") not in {"approved_source", "manual_review"}:
        return False, "contact source still needs compliance review"
    return True, "eligible for human review; no automatic send"


def score_lead(lead: dict[str, Any], today: date = TODAY) -> LeadResult:
    evidence = [parse_evidence(item) for item in lead.get("evidence", [])]
    domain = normalize_domain(str(lead.get("domain", "")))
    verified = company_verified(lead, evidence)
    excluded = is_excluded(lead)
    current = has_current_signal(evidence, today)
    independent_sources = {e.source_type for e in evidence if e.url and e.excerpt}
    usable_evidence = [e for e in evidence if e.url and e.excerpt and e.observed_date]

    score = 0
    reasons: list[str] = []
    gates: list[str] = []

    product_fit = str(lead.get("product_fit", "")).lower()
    if any(term in product_fit for term in ("packaging", "food processing", "包装", "食品加工")):
        score += 25
        reasons.append("product matches packaging/food-processing equipment focus (+25)")
    elif any(term in product_fit for term in ("fabric", "textile", "woven", "knitted", "apparel", "home textile", "workwear", "uniform", "poly-cotton", "面料", "纺织", "梭织", "针织", "工装", "制服")):
        score += 25
        reasons.append("product matches textile-fabric export focus (+25)")
    elif product_fit:
        score += 10
        reasons.append("adjacent product category (+10)")
    else:
        gates.append("missing product fit")

    signal_points = {
        "supplier_request": 30,
        "supplier_registration": 30,
        "supplier_inquiry": 30,
        "plant_expansion": 25,
        "warehouse_expansion": 25,
        "seasonal_sourcing": 25,
        "new_product_line": 20,
        "new_collection": 20,
        "relevant_hiring": 15,
        "quality_hiring": 15,
        "trade_fair": 10,
        "import_activity": 15,
        "distributor_gap": 20,
        "assortment_gap": 20,
    }
    signal_total = 0
    seen_signals: set[str] = set()
    for item in evidence:
        if item.signal in signal_points and item.signal not in seen_signals:
            signal_total += signal_points[item.signal]
            seen_signals.add(item.signal)
    signal_total = min(signal_total, 30)
    score += signal_total
    if signal_total:
        reasons.append(f"intent signals contribute +{signal_total}")
    else:
        gates.append("no recognized intent signal")

    recent_points = freshness_points(evidence, today)
    score += recent_points
    if recent_points:
        reasons.append(f"freshest evidence contributes +{recent_points}")
    else:
        gates.append("no current evidence within 90 days")

    if verified:
        score += 20
        reasons.append("company has domain and an authoritative source (+20)")
    else:
        gates.append("company could not be verified from an authoritative source")

    size = str(lead.get("size", "")).lower()
    if size in {"medium", "large", "20-300", "50-500"}:
        score += 15
        reasons.append("size suggests a plausible B2B buying process (+15)")
    elif size:
        score += 5
        reasons.append("size is present but weaker (+5)")
    else:
        gates.append("missing company size")

    if excluded:
        gates.append("excluded business type")
    if not domain:
        gates.append("missing domain")
    if len(seen_signals) < 2:
        gates.append("fewer than two distinct intent signals")
    if len(independent_sources) < 2:
        gates.append("evidence is not cross-checked across two source types")
    if not usable_evidence:
        gates.append("evidence lacks dated excerpt and URL")

    contact_ok, contact_reason = contact_gate(lead)
    if not contact_ok:
        gates.append(contact_reason)

    confidence = evidence_confidence(evidence, verified)
    if score >= 75 and not gates and confidence == "high":
        grade = "A"
        action = "human review, then prepare a one-to-one outreach brief"
    elif score >= 55 and not excluded:
        grade = "B"
        action = "enrich evidence or wait for a second current signal"
    else:
        grade = "C"
        action = "archive or suppress; do not contact"

    if grade == "A" and not contact_ok:
        grade = "B"
        action = "commercially promising, but contact route needs compliance approval"

    return LeadResult(
        company=str(lead.get("company", "")).strip(),
        domain=domain,
        country=str(lead.get("country", "")).strip(),
        buyer_type=str(lead.get("buyer_type", "")).strip(),
        product_fit=str(lead.get("product_fit", "")).strip(),
        score=min(score, 100),
        grade=grade,
        evidence_confidence=confidence,
        verified=verified,
        eligible_for_contact_review=contact_ok and grade == "A",
        reasons=reasons,
        hard_gates_failed=sorted(set(gates)),
        evidence=[asdict(e) for e in evidence],
        next_action=action,
        human_label=str(lead.get("human_label", "")),
        annotation_reason=str(lead.get("annotation_reason", "")),
        annotation_reviewer=str(lead.get("annotation_reviewer", "")),
        synthetic_demo=bool(lead.get("synthetic_demo", False)),
    )


def deduplicate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge records on domain, keeping the richer evidence set."""
    merged: dict[str, dict[str, Any]] = {}
    duplicate_notes: list[str] = []
    for record in records:
        domain = normalize_domain(str(record.get("domain", "")))
        key = f"domain:{domain}" if domain else f"name:{normalize_company(str(record.get('company', '')))}"
        if key not in merged:
            clone = dict(record)
            clone["evidence"] = list(record.get("evidence", []))
            merged[key] = clone
            continue
        existing = merged[key]
        existing_urls = {str(e.get("url", "")) for e in existing.get("evidence", [])}
        for item in record.get("evidence", []):
            if item.get("url") not in existing_urls:
                existing.setdefault("evidence", []).append(item)
        duplicate_notes.append(f"merged duplicate record for {record.get('company', '')} into {existing.get('company', '')}")
        if len(record.get("evidence", [])) > len(existing.get("evidence", [])):
            existing["description"] = record.get("description", existing.get("description", ""))
    return list(merged.values()), duplicate_notes


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("input JSON must be a list of lead records")
    return data


def run(input_path: Path) -> dict[str, Any]:
    raw = load_records(input_path)
    unique, duplicate_notes = deduplicate(raw)
    results = [score_lead(record) for record in unique]
    results.sort(key=lambda result: (-result.score, result.company.lower()))
    counts = {grade: sum(result.grade == grade for result in results) for grade in ("A", "B", "C")}
    annotation_counts: dict[str, int] = {}
    confusion: dict[str, int] = {}
    mismatches: list[dict[str, str]] = []
    for result in results:
        label = result.human_label or "unlabeled"
        annotation_counts[label] = annotation_counts.get(label, 0) + 1
        human_bucket = label.split("_", 1)[0] if label else "unlabeled"
        model_bucket = result.grade
        confusion_key = f"model_{model_bucket}__human_{human_bucket}"
        confusion[confusion_key] = confusion.get(confusion_key, 0) + 1
        if human_bucket not in {"unlabeled", model_bucket}:
            mismatches.append({
                "company": result.company,
                "model_grade": model_bucket,
                "human_label": label,
                "reason": result.annotation_reason,
            })
    focus_terms = " ".join(str(record.get("product_fit", "")) for record in unique).lower()
    focus = "WorkTex 65/35 workwear textile export accounts" if any(term in focus_terms for term in ("textile", "fabric", "workwear", "uniform", "poly-cotton", "面料", "工装", "制服")) else "packaging and food-processing equipment exporters / overseas buyers"
    return {
        "run_date": TODAY.isoformat(),
        "data_mode": "synthetic_demo" if unique and all(bool(record.get("synthetic_demo", False)) for record in unique) else "mixed_or_review_required",
        "focus": focus,
        "automation_policy": "research and scoring only; no crawling or outbound sending",
        "input_records": len(raw),
        "unique_records": len(unique),
        "duplicates_merged": len(raw) - len(unique),
        "duplicate_notes": duplicate_notes,
        "grade_counts": counts,
        "annotation_counts": annotation_counts,
        "model_human_confusion": confusion,
        "annotation_mismatches": mismatches,
        "contact_review_queue": [asdict(result) for result in results if result.eligible_for_contact_review],
        "results": [asdict(result) for result in results],
    }


def write_csv(report: dict[str, Any], path: Path) -> None:
    fields = [
        "company", "domain", "country", "buyer_type", "product_fit", "score", "grade",
        "evidence_confidence", "verified", "eligible_for_contact_review", "human_label", "annotation_reason", "hard_gates_failed", "next_action",
        "synthetic_demo",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in report["results"]:
            row = {key: item.get(key) for key in fields}
            row["hard_gates_failed"] = "; ".join(item["hard_gates_failed"])
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the export-sales intelligence MVP")
    parser.add_argument("input", type=Path, help="JSON evidence records")
    parser.add_argument("--json-out", type=Path, default=Path("report.json"))
    parser.add_argument("--csv-out", type=Path, default=Path("report.csv"))
    args = parser.parse_args()
    report = run(args.input)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report, args.csv_out)
    print(json.dumps({
        "run_date": report["run_date"],
        "input_records": report["input_records"],
        "unique_records": report["unique_records"],
        "duplicates_merged": report["duplicates_merged"],
        "grade_counts": report["grade_counts"],
        "contact_review_queue": [x["company"] for x in report["contact_review_queue"]],
        "json_out": str(args.json_out),
        "csv_out": str(args.csv_out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
