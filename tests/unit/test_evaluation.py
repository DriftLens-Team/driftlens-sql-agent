"""Verify evaluator discrimination without spending real provider calls."""

import unittest

from evaluation.cases import ROWS, corpus, expected, variants
from evaluation.run import score
from driftlens_sql_agent.errors import AgentError


def response(case, sql, value):
    return {"request_id": case["request"]["request_id"], "status": "ok", "observation": {
        "sql": sql, "answer_text": f"이번 주 대형 주문은 {value}건입니다.",
        "definition_note": f"주문 총액 {case['threshold']}센트 이상인 주문",
        "reported_values": [{"concept_id": "large_orders", "period": case["request"]["period"], "value": value}],
        "referenced_concepts": ["large_orders"]}}


class EvaluationTests(unittest.TestCase):
    def test_fixed_corpus_and_gates(self):
        cases = corpus()
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(c["supported"] for c in cases) * 3, 36)
        self.assertEqual(sum(not c["supported"] for c in cases) * 3, 24)
        self.assertEqual(len({c["request"]["request_id"] for c in cases}), 20)
        self.assertEqual([expected(ROWS, p, t) for p in ["2025-W03", "2025-W04"] for t in [2000, 3000]], [5, 2, 3, 2])

    def test_valid_sql_and_accidental_right_answer(self):
        case = corpus()[0]
        sql = "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND ordered_at < '2025-01-20' AND order_total_cents >= 2000"
        self.assertTrue(score(case, response(case, sql, 5))["passed"])
        # Same base result, wrong meaning: must fail on distinguishing fixtures.
        result = score(case, response(case, "SELECT 5", 5))
        self.assertEqual(result["reason"], "sql_semantics")
        self.assertFalse(result["passed"])
        result = score(case, response(case, sql, True))
        self.assertFalse(result["protocol_ok"])

    def test_refusal_and_information_boundaries(self):
        case = corpus()[-1]
        result = {"request_id": case["request"]["request_id"], "status": "error",
                  "error": AgentError("unsupported_request").record()}
        self.assertTrue(score(case, result)["passed"])
        result["error"]["message"] = "SECRET"
        self.assertFalse(score(case, result, secret="SECRET")["information_ok"])
        result = response(corpus()[0], "SELECT 5 -- SECRET", 5)
        self.assertFalse(score(corpus()[0], result, secret="SECRET")["passed"])
        result["observation"]["sql"] = "SELECT 5 -- truth.jsonl"
        self.assertFalse(score(corpus()[0], result, private_markers=["truth.jsonl"])["passed"])

    def test_variants_discriminate_boundary(self):
        base = expected(ROWS, "2025-W03", 2000)
        values = [expected(rows, "2025-W03", 2000) for rows in variants("2025-W03", 2000)]
        self.assertEqual(values, [0, 0, base + 1, base, base, base + 1])
