import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import run
from src.knowledge import DEFAULT_CORPUS, Knowledge
from src.main import load_request
from src.models import ChatModel, MockModel, final, tool


EXAMPLES = DEFAULT_CORPUS.parent.parent / "examples"


class AgentTests(unittest.TestCase):
    def check(self, case, status, *, fault=None, max_steps=10, corpus=DEFAULT_CORPUS):
        result = run(MockModel(), Knowledge(corpus, fault=fault),
                     load_request(EXAMPLES / f"{case}.input.json"), max_steps)
        self.assertEqual(result["status"], status)
        for citation in result["citations"]:
            self.assertEqual(citation, Knowledge(corpus).read(citation["doc_id"], citation["passage_id"]))
        return result

    def test_explicit_answer(self):
        result = self.check("normal", "answered")
        self.assertIn("Guest-WiFi", result["answer"])
        self.assertEqual(result["citations"][0]["doc_id"], "D03")
        self.assertEqual([step["action"] for step in result["trace"]], ["search", "read", "finish"])

    def test_conflict_reads_both_and_searches_for_resolution(self):
        result = self.check("conflict", "conflict")
        self.assertEqual({item["doc_id"] for item in result["citations"]}, {"D01", "D02"})
        self.assertIn("30 天", result["answer"])
        self.assertIn("15 天", result["answer"])
        self.assertIn("请向制度负责人确认", result["answer"])
        self.assertEqual([step["action"] for step in result["trace"]],
                         ["search", "read", "read", "search", "finish"])

    def test_finish_feedback_requires_candidate_coverage_and_conflict_verification(self):
        class PrematureFinish(MockModel):
            def decide(self, request, observations, remaining):
                reads = [item["result"] for item in observations if item["action"] == "read"]
                if len(observations) == 2:
                    return final("answered", "30 天", "", "只读到第一条", reads)
                if len(observations) == 4:
                    return final("conflict", "30 天或 15 天，请确认。", "优先级未知。",
                                 "观察到冲突", reads)
                return super().decide(request, observations, remaining)

        result = run(PrematureFinish(), Knowledge(), load_request(EXAMPLES / "conflict.input.json"), 10)
        self.assertEqual(result["status"], "conflict")
        first_feedback = result["trace"][2]["observation"]
        self.assertFalse(first_feedback["ok"])
        self.assertEqual(first_feedback["unread"], [{"doc_id": "D02", "passage_id": "p1"}])
        self.assertFalse(result["trace"][4]["observation"]["ok"])
        self.assertEqual(result["trace"][4]["next_action"], "search")

    def test_out_of_scope_searches_again(self):
        result = self.check("missing", "insufficient_evidence")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["trace"][0]["next_action"], "search")

        class StopsAfterFirstSearch(MockModel):
            def decide(self, request, observations, remaining):
                if len(observations) == 1:
                    return final("insufficient_evidence", "公司没有这项制度。", "未命中。", "没有证据")
                if len(observations) == 2:
                    return tool("search", "换个关键词", query="宠物保障", limit=5)
                return super().decide(request, observations, remaining)

        guarded = run(StopsAfterFirstSearch(), Knowledge(),
                      load_request(EXAMPLES / "missing.input.json"), 10)
        self.assertEqual(guarded["status"], "insufficient_evidence")
        self.assertFalse(guarded["trace"][1]["observation"]["ok"])
        self.assertEqual(guarded["trace"][1]["next_action"], "search")
        self.assertIn("当前知识库", guarded["answer"])

    def test_paraphrase_and_retrieval_baseline(self):
        result = self.check("paraphrase", "answered")
        self.assertEqual(result["citations"][0]["doc_id"], "D03")
        query = load_request(EXAMPLES / "paraphrase.input.json")["question"]
        self.assertEqual(Knowledge(expand=False).search(query, 5)["hits"], [])

    def test_followup_uses_history_but_cites_corpus(self):
        result = self.check("followup", "answered")
        self.assertIn("1080p", result["answer"])
        self.assertIn("基础版", result["trace"][0]["args"]["query"])
        self.assertEqual(result["citations"][0]["doc_id"], "D04")

    def test_search_failure(self):
        result = self.check("tool-failure", "tool_error", fault="search")
        self.assertFalse(result["trace"][0]["observation"]["ok"])
        self.assertEqual(result["citations"], [])

    def test_read_failure(self):
        result = self.check("tool-failure", "tool_error", fault="read")
        self.assertFalse(result["trace"][1]["observation"]["ok"])
        self.assertEqual(result["citations"], [])

    def test_wrong_action_name_can_be_corrected_after_tool_failure(self):
        class WrongAction(MockModel):
            def decide(self, request, observations, remaining):
                if len(observations) == 1:
                    return {"action": "tool_error", "reason": "检索失败"}
                return super().decide(request, observations, remaining)

        result = run(WrongAction(), Knowledge(fault="search"),
                     load_request(EXAMPLES / "tool-failure.input.json"), 5)
        self.assertEqual(result["status"], "tool_error")
        self.assertEqual([item["action"] for item in result["trace"]], ["search", "tool_error", "finish"])
        self.assertFalse(result["trace"][1]["observation"]["ok"])

    def test_step_budget(self):
        result = self.check("normal", "step_limit", max_steps=1)
        self.assertEqual(len(result["trace"]), 1)
        self.assertEqual(result["trace"][0]["next_action"], "step_limit")
        self.assertEqual(result["citations"], [])

    def test_changed_documents_change_actions_and_answer(self):
        result = self.check("conflict", "answered", corpus=EXAMPLES / "revised.corpus.json")
        self.assertIn("45 天", result["answer"])
        self.assertEqual([step["action"] for step in result["trace"]], ["search", "read", "finish"])

    def test_forged_citation_rejected(self):
        class Forged(MockModel):
            def decide(self, request, observations, remaining):
                return final("answered", "伪造答案", "", "伪造引用",
                             [{"doc_id": "D03", "passage_id": "p1"}])

        result = run(Forged(), Knowledge(), load_request(EXAMPLES / "normal.input.json"), 5)
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(result["citations"], [])

    def test_invalid_read_is_not_executed(self):
        class InvalidRead(MockModel):
            def decide(self, request, observations, remaining):
                return tool("read", "跳过检索", doc_id="D03", passage_id="p1")

        result = run(InvalidRead(), Knowledge(), load_request(EXAMPLES / "normal.input.json"), 5)
        self.assertEqual(result["status"], "model_error")

    def test_http_adapter_sends_observations_back_to_model(self):
        state = []
        decisions = [
            tool("search", "定位文档", query="访客网络", limit=4),
            tool("read", "核对原文", doc_id="D03", passage_id="p1"),
            final("answered", "请连接 Guest-WiFi 并由接待员工申请访问码。", "", "原文支持",
                  [{"doc_id": "D03", "passage_id": "p1"}]),
        ]

        def simulated_endpoint(http_request, timeout):
            self.assertEqual(http_request.full_url, "http://localhost:8080/v1/chat/completions")
            payload = json.loads(http_request.data)
            index = len(state)
            state.append(json.loads(payload["messages"][1]["content"]))
            return io.BytesIO(json.dumps({
                "choices": [{"message": {"content": json.dumps(decisions[index])}}]
            }).encode("utf-8"))

        settings = {"MODEL_NAME": "stub", "MODEL_BASE_URL": "http://localhost:8080/v1"}
        with patch.dict("os.environ", settings, clear=True):
            with patch("urllib.request.urlopen", side_effect=simulated_endpoint):
                result = run(ChatModel(), Knowledge(), load_request(EXAMPLES / "normal.input.json"), 5)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(state[0]["observations"], [])
        self.assertEqual(state[1]["observations"][0]["result"]["hits"][0]["doc_id"], "D03")
        self.assertIn("Guest-WiFi", state[2]["observations"][-1]["result"]["text"])
        self.assertEqual([entry["remaining_steps"] for entry in state], [5, 4, 3])

    def test_bad_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"question":"x","history":[null]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_request(path)
