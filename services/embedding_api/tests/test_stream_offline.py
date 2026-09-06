"""Offline contract tests: no GPU, model files, database or pytest required.

Run: python -m unittest discover -s services/embedding_api/tests -p test_stream_offline.py -v
"""
import ast
import asyncio
from contextlib import contextmanager
import importlib.util
import json
import logging
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

APP = Path(__file__).resolve().parents[1] / "app"


def load_class(path, name, namespace):
    # Execute the actual class without importing GPU/database singletons.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


spec = importlib.util.spec_from_file_location("bridge", APP / "services/infra/query_stream.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class StreamTests(unittest.TestCase):
    def llm(self):
        return load_class(APP / "services/infra/llm_service.py", "LlmService",
                          dict(contextmanager=contextmanager, json=json, LLMException=RuntimeError))()

    def test_sse_japanese_and_terminal(self):
        lines = [': keepalive', '', 'data: {"content":"継承","stop":false}', '',
                 'data: {"content":"です","stop":true}', '']
        response = Mock()
        response.iter_lines.return_value = [x.encode() for x in lines]
        self.assertEqual(list(self.llm()._read_tokens(response)), ["継承", "です"])

    def test_truncated_sse_fails(self):
        response = Mock()
        response.iter_lines.return_value = [b'data: {"content":"x"}', b'']
        with self.assertRaises(RuntimeError):
            list(self.llm()._read_tokens(response))

    def test_malformed_sse_fails(self):
        response = Mock()
        response.iter_lines.return_value = [b'data: invalid', b'']
        with self.assertRaises(ValueError):
            list(self.llm()._read_tokens(response))

    def test_upstream_error(self):
        response = Mock()
        response.iter_lines.return_value = [b'data: {"error":"secret"}', b'']
        with self.assertRaises(RuntimeError):
            list(self.llm()._read_tokens(response))

    def service(self, empty=False, none=False):
        item = NS(document="資料", metadata={"document_id": "d", "chunk_no": 1},
                  page_reference=None)
        status = NS(value="NONE" if none else "FULL")
        ns = dict(logging=logging, time=time, logger=logging.getLogger("test"),
                  AnswerabilityResult=object, AnswerabilityStatus=NS(NONE=status if none else object()),
                  LearningFollowUpService=Mock(return_value=Mock(generate=Mock(return_value=[]))))
        for name in ["query_normalizer", "collection_router_service", "progress_service",
                     "off_topic_router_service", "conversation_service", "query_rewrite_service",
                     "answerability_gate_service", "context_dedup_service",
                     "learning_response_controller", "prompt_builder", "llm_service",
                     "search_log_service"]:
            ns[name] = Mock()
        ns["query_normalizer"].normalize.return_value = "継承とは"
        ns["query_rewrite_service"].analyze.return_value = ("継承", "EXPLAIN")
        ns["answerability_gate_service"].assess.return_value = NS(status=status, reason="test")
        ns["context_dedup_service"].deduplicate.return_value = [item]
        ns["learning_response_controller"].decide.return_value = NS(answer_level=NS(value="brief"))
        ns["llm_service"].ask.return_value = "継承です"
        @contextmanager
        def tokens(prompt):
            yield iter(["継承", "です"])
        ns["llm_service"].stream.side_effect = tokens
        cls = load_class(APP / "services/query_service.py", "QueryService", ns)
        service = cls()
        candidates = [] if empty else [item]
        service._search_and_rerank = Mock(return_value=(
            NS(total=len(candidates), cache_hit=False, items=candidates), candidates, candidates, 0))
        return service, ns

    def test_shared_pipeline_compatibility(self):
        service, ns = self.service()
        normal = service.ask("継承")
        events = list(service.stream("継承"))
        final = events[-1]["result"]
        self.assertEqual(normal["answer"], final["answer"])
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "token"), final["answer"])
        self.assertEqual([e["stage"] for e in events if e["type"] == "status"],
                         ["analysis", "retrieval", "answerability", "generation"])
        self.assertEqual(ns["llm_service"].ask.call_count, 1)

    def test_empty_retrieval_completes_without_llm(self):
        service, ns = self.service(empty=True)
        events = list(service.stream("継承"))
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["result"]["metadata"]["retrieved_count"], 0)
        ns["llm_service"].stream.assert_not_called()

    def test_gate_none_completes_without_generation(self):
        service, ns = self.service(none=True)
        events = list(service.stream("継承"))
        self.assertEqual(events[-1]["result"]["answerability_status"], "NONE")
        ns["llm_service"].stream.assert_not_called()

    def test_cancel_during_tokens_skips_history(self):
        service, ns = self.service()
        cancelled = threading.Event()
        events = service.stream("継承", cancelled=cancelled)
        for event in events:
            if event["type"] == "token":
                cancelled.set()
                break
        with self.assertRaises(GeneratorExit):
            next(events)
        ns["conversation_service"].append.assert_not_called()

    def test_bridge_complete(self):
        async def run():
            request = NS(is_disconnected=Mock(side_effect=lambda: asyncio.sleep(0, result=False)))
            def factory(cancelled):
                yield {"type": "token", "text": "日本語"}
                yield {"type": "result", "result": {"answer": "日本語"}}
            serialize = lambda result: NS(model_dump=lambda **kw: result)
            return [json.loads(line) async for line in bridge.ndjson_events(factory, serialize, request)]
        events = asyncio.run(run())
        self.assertEqual(events[-1], {"type": "complete", "answer": "日本語"})

    def test_bridge_error_hides_details(self):
        async def run():
            request = NS(is_disconnected=Mock(side_effect=lambda: asyncio.sleep(0, result=False)))
            def factory(cancelled):
                raise RuntimeError("secret")
                yield
            return [json.loads(line) async for line in bridge.ndjson_events(factory, None, request)]
        events = asyncio.run(run())
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("secret", str(events))

    def test_heartbeat_during_slow_work(self):
        async def run():
            request = NS(is_disconnected=Mock(side_effect=lambda: asyncio.sleep(0, result=False)))
            def factory(cancelled):
                time.sleep(0.15)
                yield {"type": "result", "result": {"answer": "done"}}
            serialize = lambda result: NS(model_dump=lambda **kw: result)
            return [json.loads(line) async for line in
                    bridge.ndjson_events(factory, serialize, request, heartbeat_seconds=0.01)]
        events = asyncio.run(run())
        self.assertIn("heartbeat", [e["type"] for e in events])
        self.assertEqual(events[-1]["type"], "complete")

    def test_disconnect_closes_worker(self):
        closed = threading.Event()
        async def run():
            request = NS(is_disconnected=Mock(side_effect=lambda: asyncio.sleep(0, result=True)))
            def factory(cancelled):
                try:
                    while not cancelled.is_set():
                        time.sleep(0.01)
                        yield {"type": "token", "text": "x"}
                finally:
                    closed.set()
            async for _ in bridge.ndjson_events(factory, None, request):
                pass
        asyncio.run(run())
        self.assertTrue(closed.wait(1))


if __name__ == "__main__":
    unittest.main()
