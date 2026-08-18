import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from worktex_pipeline import export_report, ingest, init_db


class WorkTexPipelineTests(unittest.TestCase):
    def test_ingest_persists_leads_evidence_and_skill_runs(self):
        seed = Path(__file__).with_name("worktex_real_leads_seed.json")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "pipeline.db"
            out_path = Path(tmp) / "export.json"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                init_db(conn)
                summary = ingest(conn, seed)
                self.assertEqual(summary["unique_records"], 8)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 8)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM skill_runs").fetchone()[0], 64)
                export_report(conn, out_path)
            exported = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["count"], 8)
            self.assertEqual(len(exported["leads"][0]["skill_runs"]), 8)


if __name__ == "__main__":
    unittest.main()
