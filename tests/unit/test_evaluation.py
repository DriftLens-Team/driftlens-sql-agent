"""Verify evaluator discrimination without spending real provider calls."""

import unittest

from evaluation.cases import ROWS, corpus, expected
from evaluation.run import score
from driftlens_sql_agent.errors import AgentError


def response(case, sql, value):
    """테스트에서 사용할 응답을 준비한다. 실제 네트워크 자격 증명은 사용하지 않는다."""
    return {"request_id": case["request"]["request_id"], "status": "ok", "observation": {
        "sql": sql, "answer_text": f"이번 주 대형 주문은 {value}건입니다.",
        "definition_note": f"주문 총액 {case['threshold']}센트 이상인 주문",
        "reported_values": [{"concept_id": "large_orders", "period": case["request"]["period"], "value": value}],
        "referenced_concepts": ["large_orders"]}}


class EvaluationTests(unittest.TestCase):
    def test_fixed_corpus_and_gates(self):
        """고정 사례 수·지원 비율·정답 건수가 평가 계약과 일치하는지 확인한다."""
        cases = corpus()
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(c["supported"] for c in cases) * 3, 36)
        self.assertEqual(sum(not c["supported"] for c in cases) * 3, 24)
        self.assertEqual(len({c["request"]["request_id"] for c in cases}), 20)
        self.assertEqual([expected(ROWS, p, t) for p in ["2025-W03", "2025-W04"] for t in [2000, 3000]], [5, 2, 3, 2])

    def test_valid_sql_and_accidental_right_answer(self):
        """올바른 SQL은 통과하고 우연히 정답만 맞춘 상수 SQL은 탈락시키는지 확인한다."""
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
        """미지원 거부와 비밀·평가 내부 정보의 노출 감지를 확인한다."""
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
        # 기본 데이터의 정답이 우연히 같아도 시작일·종료일·임계값 오류를 거른다.
        """날짜·금액의 비교 연산자가 잘못된 SQL을 평가가 거부하는지 확인한다."""
        case = corpus()[0]
        for sql in [
            "SELECT COUNT(*) FROM orders WHERE ordered_at > '2025-01-13' AND ordered_at < '2025-01-20' AND order_total_cents >= 2000",
            "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND ordered_at <= '2025-01-20' AND order_total_cents >= 2000",
            "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND ordered_at < '2025-01-20' AND order_total_cents > 2000",
        ]:
            with self.subTest(sql=sql):
                self.assertFalse(score(case, response(case, sql, 5))["passed"])
