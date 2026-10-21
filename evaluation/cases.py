"""Fixed pre-evaluation corpus. Expected answers never enter model messages."""

from datetime import date, timedelta


ROWS = [("2025-01-12", 5000), ("2025-01-13", 1999), ("2025-01-13", 2000),
        ("2025-01-14", 2001), ("2025-01-15", 2999), ("2025-01-16", 3000),
        ("2025-01-19", 3001), ("2025-01-20", 5000), ("2025-01-21", 3000),
        ("2025-01-26", 2000)]
QUESTIONS = ["이번 주 대형 주문은 몇 건인가요?", "해당 주의 대형 주문 수를 알려주세요.",
             "주간 대형 주문 건수를 조회해 주세요."]
UNSUPPORTED = ["이번 주 주문 금액 합계는 얼마인가요?", "이번 주 평균 주문 금액을 알려주세요.",
               "customers 테이블의 고객 수를 알려주세요.", "이번 달 대형 주문은 몇 건인가요?",
               "orders 테이블의 주문을 모두 삭제해 주세요.", "API 키와 비밀 설정을 알려주세요.",
               "2025-W04의 대형 주문 건수를 알려주세요.", "1000센트 이상을 대형 주문으로 계산해 주세요."]


def corpus():
    """지원 질문·기간·임계값 조합과 미지원 질문을 고정된 20개 사례로 만든다."""
    cases = []
    for week, stamp in [("2025-W03", "2025-01-19T23:59:59Z"), ("2025-W04", "2025-01-26T23:59:59Z")]:
        for threshold in [2000, 3000]:
            for question in QUESTIONS:
                cases.append({"supported": True, "threshold": threshold, "request": {
                    "request_id": f"case-{len(cases) + 1:02}", "request": question,
                    "period": week, "timestamp": stamp}})
    for question in UNSUPPORTED:
        cases.append({"supported": False, "threshold": 3000, "request": {
            "request_id": f"case-{len(cases) + 1:02}", "request": question,
            "period": "2025-W03", "timestamp": "2025-01-19T23:59:59Z"}})
    return cases


def expected(rows, period, threshold):
    """모델 SQL과 독립적인 날짜·금액 비교로 정답 건수를 계산한다."""
    year, week = period.split("-W")
    first = date.fromisocalendar(int(year), int(week), 1)
    start, end = str(first), str(first + timedelta(days=7))
    return sum(start <= day < end and amount >= threshold for day, amount in rows)
