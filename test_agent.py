from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from agent import AgentError, FakeModel, UpstageModel, run_agent


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'orders.sqlite'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)')
            db.executemany('INSERT INTO orders VALUES(?,?,?)',[('a','2025-01-13',2000),('b','2025-01-13',3000)])
        db.close()

    def tearDown(self): self.tmp.cleanup()

    def test_fake_loop_reads_actual_stale_sql_result(self):
        sql='SELECT COUNT(*) FROM orders WHERE order_total_cents >= 2000'
        result=run_agent(self.db,'건수?',FakeModel(sql))
        self.assertEqual(result['reported_value'],2)
        self.assertEqual(result['sql_query'],sql)
        self.assertIn('2',result['answer_text'])

    def test_error_recovery(self):
        actions=iter([{'action':'query','sql':'DELETE FROM orders'},
                      {'action':'query','sql':'SELECT COUNT(*) FROM orders'},
                      {'action':'answer','answer_text':'주문은 2건입니다.'}])
        self.assertEqual(run_agent(self.db,'?',lambda _:next(actions))['reported_value'],2)

    def test_reject_ungrounded_answer_and_wrong_numbers(self):
        with self.assertRaises(AgentError):
            run_agent(self.db,'?',lambda _:{'action':'answer','answer_text':'2건'})
        actions=iter([{'action':'query','sql':'SELECT COUNT(*) FROM orders'},
                      {'action':'answer','answer_text':'3건'}])
        with self.assertRaises(AgentError): run_agent(self.db,'?',lambda _:next(actions))

    def test_budget_and_malformed_action(self):
        with self.assertRaisesRegex(AgentError,'turn_limit'):
            run_agent(self.db,'?',lambda _:{'action':'query','sql':'SELECT COUNT(*) FROM orders'},max_turns=2)
        with self.assertRaises(AgentError): run_agent(self.db,'?',lambda _:['invalid'])

    def test_failed_query_invalidates_previous_count(self):
        actions=iter([{'action':'query','sql':'SELECT COUNT(*) FROM orders'},
                      {'action':'query','sql':'SELECT * FROM private_truth'},
                      {'action':'answer','answer_text':'2건'}])
        with self.assertRaises(AgentError): run_agent(self.db,'?',lambda _:next(actions))

    def test_missing_credentials_no_fallback(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaises(AgentError): UpstageModel()


if __name__=='__main__': unittest.main()
