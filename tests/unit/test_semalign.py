"""Independent hand-counted v2 fixtures and unchanged v1 process behavior."""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from driftlens_sql_agent.errors import AgentError
from driftlens_sql_agent.runtime import Runtime
from driftlens_sql_agent.semalign import SemAlignBudgets, SemAlignProfile, SemAlignRequest, metric_answer, metric_value
from driftlens_sql_agent.settings import Settings, load_settings
from driftlens_sql_agent.sql_access import query

REQUEST = {"request_id": "r1", "request": "해당 주 값을 알려줘", "concept_id": "sa_order_value_avg",
           "timestamp": "2025-01-21T10:00:00Z", "window": {"start": "2025-01-13T00:00:00Z", "end": "2025-01-20T00:00:00Z"},
           "as_of": "2025-01-20T00:00:00Z"}


class SemAlignTests(unittest.TestCase):
    def setUp(self):
        """unittest hook builds an invented DB with a mixed and an itemless order."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "test.sqlite"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE orders(order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, ordered_at TEXT NOT NULL,
                    location_id TEXT NOT NULL, subtotal_cents INTEGER NOT NULL, tax_paid_cents INTEGER NOT NULL, order_total_cents INTEGER NOT NULL);
                CREATE TABLE order_items(order_item_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, product_id TEXT NOT NULL);
                CREATE TABLE products(product_id TEXT PRIMARY KEY, product_name TEXT, product_type TEXT, product_price_cents INTEGER, product_description TEXT);
                CREATE TABLE locations(location_id TEXT PRIMARY KEY, location_name TEXT, opened_at TEXT, tax_rate REAL);
                CREATE TABLE private_truth(secret TEXT);
                INSERT INTO products VALUES('f','Food','jaffle',100,NULL),('b','Drink','beverage',100,NULL),('x','Other','other',100,NULL);
                INSERT INTO orders VALUES
                    ('p0','A','2025-01-05T00:00:00','s',0,0,0),
                    ('p1','A','2025-01-06T00:00:00','s',100,10,110), ('p2','B','2025-01-08T00:00:00','s',300,30,330),
                    ('q1','A','2025-01-13T00:00:00','s',100,10,110), ('q2','A','2025-01-14T00:00:00','s',200,20,220),
                    ('q3','C','2025-01-15T00:00:00','s',0,0,0), ('q4','D','2025-01-16T00:00:00','s',300,30,330),
                    ('q5','E','2025-01-19T23:59:59','s',400,40,440);
                INSERT INTO order_items VALUES('i1','q1','f'),('i2','q1','b'),('i3','q2','f'),('i4','q2','f'),('i5','q4','b'),('i6','q5','f');
            """)
        db.close()
        self.slots = {"grain":"order", "aggregation":"average", "population":"all", "measure":"subtotal_cents",
                      "conditions":"none", "time_semantics":"week", "null_policy":"sql_null", "unit":"cents"}
        self.profile = SemAlignProfile("sa_order_value_avg", "객단가", "해당 기간 주문의 세전 금액 평균", "cents", self.slots)
        self.settings = Settings(self.db, self.profile, SemAlignBudgets(), "fake", protocol="v2")

    def test_all_families_and_current_profile(self):
        """Hand values distinguish item multiplicity, active threshold and tax basis."""
        cases = [
            ("sa_food_orders","count",{"population":"contains:jaffle"},3),
            ("sa_food_orders","count",{"population":"only:jaffle"},2),
            ("sa_drink_orders","count",{"population":"contains:beverage"},2),
            ("sa_customers_active","count",{"conditions":"min_orders:1"},4),
            ("sa_customers_active","count",{"conditions":"min_orders:2"},1),
            ("sa_customers_new","count",{},3),
            ("sa_order_value_avg","cents",{},200),
            ("sa_order_value_avg","cents",{"measure":"order_total_cents"},220),
            ("sa_revenue_growth_wow","ratio",{},1.5),
            ("sa_tax_rate_avg","ratio",{},0.1),
        ]
        for cid, unit, patch, expected in cases:
            with self.subTest(cid=cid, patch=patch):
                profile = replace(self.profile, concept_id=cid, unit=unit, semantics={**self.slots, "unit":unit, **patch})
                runtime = Runtime(replace(self.settings, profile=profile))
                response = runtime.run({**REQUEST, "concept_id":cid})
                self.assertEqual(response["status"], "ok", response)
                observation = response["observation"]
                self.assertEqual(observation["reported_values"][0]["value"], expected)
                self.assertEqual(observation["definition_note"], profile.definition)
                self.assertNotIn("version", str(observation))

    def test_request_contract_and_profile_binding(self):
        """Reject bad timezone, partial weeks, extra fields and the wrong current metric."""
        self.assertEqual(SemAlignRequest.parse(REQUEST).start, "2025-01-13")
        bad = [{**REQUEST,"private":True}, {**REQUEST,"timestamp":"2025-01-19T23:59:59Z"},
               {**REQUEST,"as_of":"2025-01-20T00:00:00+00:00"}, {**REQUEST,"window":{**REQUEST["window"],"end":"2025-01-21T00:00:00Z"}}]
        for request in bad:
            with self.assertRaises(AgentError):
                SemAlignRequest.parse(request)
        with self.assertRaises(AgentError):
            Runtime(self.settings).run({**REQUEST,"concept_id":"sa_food_orders"})

    def test_read_only_allowlist_and_budget(self):
        """Execution authorization rejects writes, private reads, recursive and unbounded work."""
        for sql in ["DELETE FROM orders", "SELECT * FROM private_truth", "SELECT load_extension('x')",
                    "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT SUM(n) FROM x",
                    "SELECT COUNT(*) FROM orders; SELECT 1", "SELECT tax_rate FROM locations"]:
            with self.subTest(sql=sql), self.assertRaises(AgentError):
                query(self.db,sql,SemAlignBudgets(),deadline=time.monotonic()+5,protocol="v2",concept_id="sa_food_orders")
        with self.assertRaises(AgentError):
            query(self.db,"SELECT SUM(a.subtotal_cents*b.subtotal_cents) FROM orders a CROSS JOIN orders b",SemAlignBudgets(sql_vm_steps=1),deadline=time.monotonic()+5,protocol="v2",concept_id="sa_order_value_avg")

    def test_rounding_null_negative_and_answer(self):
        """Reporting uses source banker's rounding and never accepts mismatched units."""
        for raw,unit,expected in [(2.5,"cents",2),(3.5,"cents",4),(-0.12345,"ratio",-0.1235),(None,"ratio",None),(0,"count",0)]:
            self.assertEqual(metric_value({"rows":[(raw,)]},unit),expected)
            answer="계산할 수 없습니다." if expected is None else f"결과는 {expected} {unit}입니다."
            self.assertEqual(metric_answer(answer,expected,unit),answer)
        for raw in [True,1.0,-1,2**63,float("inf")]:
            with self.assertRaises(AgentError):
                metric_value({"rows":[(raw,)]},"count")
        with self.assertRaises(AgentError):
            metric_answer("결과는 0.1 cents입니다.",0.1,"ratio")

    def test_config_cli_capabilities_and_two_requests(self):
        """Real JSONL process advertises v2 and resets per-request state without API keys."""
        profile={"concept_id":self.profile.concept_id,"label":self.profile.label,"definition":self.profile.definition,
                 "unit":self.profile.unit,"semantics":self.slots}
        config={"database":{"kind":"sqlite","path":"test.sqlite","read_only":True},"schema_id":"semalign/v1",
                "model":{"provider":"fake","id_env":"TEST_MODEL","api_key_env":"TEST_KEY"}}
        cp,pp=self.root/"config.json",self.root/"profile.json"
        cp.write_text(json.dumps(config),encoding="utf-8")
        pp.write_text(json.dumps(profile),encoding="utf-8")
        self.assertEqual(load_settings(cp,pp,protocol="v2").protocol,"v2")
        with self.assertRaises(AgentError):
            load_settings(cp,pp)
        base=[sys.executable,"-m","driftlens_sql_agent"]
        cap=subprocess.run(base+["--capabilities"],capture_output=True,text=True,check=True)
        self.assertIn("agent/v2",json.loads(cap.stdout)["protocols"])
        payload="\n".join(json.dumps({**REQUEST,"request_id":rid}) for rid in ("one","two"))+"\n"
        proc=subprocess.run(base+["--config",str(cp),"--profile",str(pp),"--protocol-version","v2"],
                            input=payload.encode(),capture_output=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        responses=[json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([r["status"] for r in responses],["ok","ok"])
        self.assertEqual([r["request_id"] for r in responses],["one","two"])
