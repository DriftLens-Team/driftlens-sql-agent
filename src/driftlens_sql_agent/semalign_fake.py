"""Deterministic protocol exercise model, never a claim about language understanding."""

import json


class FakeSemAlignModel:
    """Render seven declared metric families from a current structured profile."""

    def generate(self, messages, *, timeout, max_bytes):
        """Model interface required by the isolated worker; no oracle or labels read."""
        context = json.loads(messages[1]["content"])
        profile = context["definition"]
        slots = profile["semantics"]
        if messages[-1]["content"].startswith("SQL_RESULT:"):
            value = json.loads(messages[-1]["content"][11:])["value"]
            answer = "계산할 수 없습니다." if value is None else f"결과는 {value} {profile['unit']}입니다."
            return {"action": "answer", "answer_text": answer}
        s, e = context["start"], context["end"]
        window = f"o.ordered_at >= '{s}' AND o.ordered_at < '{e}'"
        cid = context["concept_id"]
        if cid in {"sa_food_orders", "sa_drink_orders"}:
            mode, kind = slots["population"].split(":")
            if mode not in {"contains", "only"} or kind not in {"jaffle", "beverage"}:
                return {"action": "unsupported"}
            sql = ("SELECT COUNT(*) FROM orders o WHERE " + window
                   + " AND EXISTS (SELECT 1 FROM order_items i JOIN products p ON p.product_id=i.product_id"
                   + f" WHERE i.order_id=o.order_id AND p.product_type='{kind}')")
            if mode == "only":
                sql += (" AND NOT EXISTS (SELECT 1 FROM order_items i JOIN products p ON p.product_id=i.product_id"
                        + f" WHERE i.order_id=o.order_id AND p.product_type<>'{kind}')")
        elif cid == "sa_customers_active":
            rule, minimum = slots["conditions"].split(":")
            if rule != "min_orders" or not minimum.isdigit() or not 1 <= int(minimum) <= 100:
                return {"action": "unsupported"}
            sql = ("SELECT COUNT(*) FROM (SELECT o.customer_id FROM orders o WHERE " + window
                   + f" GROUP BY o.customer_id HAVING COUNT(*) >= {int(minimum)})")
        elif cid == "sa_customers_new":
            sql = ("SELECT COUNT(*) FROM (SELECT customer_id, MIN(ordered_at) AS first_at FROM orders"
                   + f" GROUP BY customer_id) WHERE first_at >= '{s}' AND first_at < '{e}'")
        elif cid == "sa_order_value_avg":
            col = slots["measure"]
            if col not in {"subtotal_cents", "order_total_cents"}:
                return {"action": "unsupported"}
            sql = f"SELECT AVG(o.{col}) FROM orders o WHERE " + window
        elif cid == "sa_tax_rate_avg":
            sql = "SELECT SUM(o.tax_paid_cents)*1.0/SUM(o.subtotal_cents) FROM orders o WHERE " + window
        elif cid == "sa_revenue_growth_wow":
            sql = (f"SELECT CASE WHEN (SELECT MIN(ordered_at) FROM orders) > date('{s}', '-7 days') THEN NULL"
                   + " ELSE (cur-prev)*1.0/prev END FROM (SELECT"
                   + f" SUM(CASE WHEN ordered_at >= '{s}' THEN subtotal_cents END) AS cur,"
                   + f" SUM(CASE WHEN ordered_at < '{s}' THEN subtotal_cents END) AS prev FROM orders"
                   + f" WHERE ordered_at >= date('{s}', '-7 days') AND ordered_at < '{e}')")
        else:
            return {"action": "unsupported"}
        return {"action": "query", "sql": sql}
