import json
import tempfile
import unittest
from pathlib import Path

from sales_intel_mvp import deduplicate, run, score_lead


class SalesIntelMvpTests(unittest.TestCase):
    def test_normalizes_domain_and_merges_duplicates(self):
        records = [
            {"company": "A Ltd", "domain": "https://www.a.example/", "evidence": []},
            {"company": "A Limited", "domain": "a.example", "evidence": [{"url": "u"}]},
        ]
        unique, notes = deduplicate(records)
        self.assertEqual(len(unique), 1)
        self.assertEqual(len(notes), 1)
        self.assertEqual(len(unique[0]["evidence"]), 1)

    def test_two_current_signals_and_authoritative_sources_can_be_a(self):
        lead = {
            "company": "A Packaging Buyer",
            "domain": "a.example",
            "country": "US",
            "buyer_type": "equipment distributor",
            "product_fit": "packaging equipment",
            "size": "medium",
            "contact_mode": "corporate_email",
            "contact_review_status": "manual_review",
            "evidence": [
                {"signal": "supplier_request", "source_type": "official_site", "url": "https://a.example/suppliers", "observed_on": "2026-08-01", "excerpt": "supplier request"},
                {"signal": "distributor_gap", "source_type": "trade_fair", "url": "https://fair.example/a", "observed_on": "2026-07-20", "excerpt": "distributor profile"},
            ],
        }
        result = score_lead(lead)
        self.assertEqual(result.grade, "A")
        self.assertTrue(result.eligible_for_contact_review)
        self.assertEqual(result.evidence_confidence, "high")

    def test_public_personal_email_does_not_pass_contact_gate(self):
        lead = {
            "company": "A Packaging Buyer",
            "domain": "a.example",
            "buyer_type": "equipment distributor",
            "product_fit": "packaging equipment",
            "size": "medium",
            "contact_mode": "named_personal_email",
            "contact_review_status": "unknown",
            "evidence": [
                {"signal": "supplier_request", "source_type": "official_site", "url": "https://a.example/suppliers", "observed_on": "2026-08-01", "excerpt": "supplier request"},
                {"signal": "distributor_gap", "source_type": "trade_fair", "url": "https://fair.example/a", "observed_on": "2026-07-20", "excerpt": "distributor profile"},
            ],
        }
        result = score_lead(lead)
        self.assertEqual(result.grade, "B")
        self.assertFalse(result.eligible_for_contact_review)
        self.assertTrue(any("contact route" in reason for reason in result.hard_gates_failed))

    def test_expired_evidence_is_not_a(self):
        lead = {
            "company": "Old Buyer",
            "domain": "old.example",
            "buyer_type": "food manufacturer",
            "product_fit": "food processing equipment",
            "size": "medium",
            "contact_mode": "official_form",
            "contact_review_status": "manual_review",
            "evidence": [
                {"signal": "plant_expansion", "source_type": "official_site", "url": "https://old.example/news", "observed_on": "2025-01-01", "excerpt": "old expansion"},
                {"signal": "trade_fair", "source_type": "trade_fair", "url": "https://fair.example/old", "observed_on": "2025-01-01", "excerpt": "old fair"},
            ],
        }
        result = score_lead(lead)
        self.assertNotEqual(result.grade, "A")
        self.assertIn("no current evidence within 90 days", result.hard_gates_failed)

    def test_sample_run_has_expected_duplicate_and_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "sample.json"
            input_path.write_text(Path("sample_leads.json").read_text(encoding="utf-8"), encoding="utf-8")
            report = run(input_path)
        self.assertEqual(report["input_records"], 8)
        self.assertEqual(report["unique_records"], 7)
        self.assertEqual(report["duplicates_merged"], 1)
        self.assertIn("Northstar Food Systems", [x["company"] for x in report["contact_review_queue"]])
        self.assertNotIn("Harborline Machinery", [x["company"] for x in report["contact_review_queue"]])

    def test_human_annotations_are_preserved_for_case_review(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "demo.json"
            input_path.write_text(Path("demo_annotated_leads.json").read_text(encoding="utf-8"), encoding="utf-8")
            report = run(input_path)
        self.assertEqual(report["input_records"], 18)
        self.assertEqual(report["annotation_counts"]["A_人工确认"], 6)
        self.assertGreater(len(report["annotation_mismatches"]), 0)
        mismatch_names = {item["company"] for item in report["annotation_mismatches"]}
        self.assertIn("Coastal Pharma Packaging", mismatch_names)


if __name__ == "__main__":
    unittest.main()
