"""Bounded model-action, tool-observation loop."""

from .knowledge import ToolError


FINAL_STATUSES = {"answered", "conflict", "needs_clarification", "insufficient_evidence", "tool_error"}


class DecisionError(ValueError):
    pass


def required_text(obj, key, *, allow_empty=False, limit=1000):
    value = obj.get(key)
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise DecisionError(f"无效字段 {key}")
    return value.strip()


def finish(decision, evidence, observations):
    status = required_text(decision, "status", limit=40)
    answer = required_text(decision, "answer")
    gap = required_text(decision, "gap", allow_empty=True)
    refs = decision.get("refs")
    if status not in FINAL_STATUSES or not isinstance(refs, list) or len(refs) > 8:
        raise DecisionError("无效结束状态或引用清单")
    citations = []
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict):
            raise DecisionError("无效引用")
        key = (required_text(ref, "doc_id", limit=40), required_text(ref, "passage_id", limit=40))
        if key not in evidence or key in seen:
            raise DecisionError("引用必须来自本轮成功读取的原文，且不得重复")
        seen.add(key)
        citations.append(evidence[key])
    if status == "answered" and (not citations or gap):
        raise DecisionError("明确答案必须引用原文，且无待确认缺口")
    if status != "answered" and not gap:
        raise DecisionError("未能明确作答时必须说明缺口")
    if status == "conflict" and len({item["doc_id"] for item in citations}) < 2:
        raise DecisionError("冲突需引用至少两份原文")
    if status == "tool_error" and not any(
        item["action"] in {"search", "read"} and not item["ok"] for item in observations
    ):
        raise DecisionError("工具失败状态必须有实际失败记录")
    if status == "insufficient_evidence":
        answer = "当前知识库未提供足够资料来回答这个问题。"
    elif status == "conflict":
        answer += "\n请向制度负责人确认你适用的规则。"
    return {"status": status, "answer": answer, "citations": citations, "evidence_gap": gap}


def review_completion(result, evidence, observations):
    """Return feedback when a provisional answer leaves competing evidence unreviewed."""
    cited_docs = {item["doc_id"] for item in result["citations"]}
    if result["status"] == "answered":
        hits = {}
        for observation in observations:
            if observation["action"] == "search" and observation["ok"]:
                hits.update((hit["doc_id"], hit) for hit in observation["result"]["hits"])
        topics = {hit["policy_topic"] for doc_id, hit in hits.items()
                  if doc_id in cited_docs and "policy_topic" in hit}
        unread = {
            (doc_id, passage_id)
            for doc_id, hit in hits.items() if hit.get("policy_topic") in topics
            for passage_id in hit["passage_ids"] if (doc_id, passage_id) not in evidence
        }
        if unread:
            return {
                "error": "同一制度事项还有未读原文。使用 read 核对 unread 中的文档与片段。",
                "unread": [{"doc_id": doc, "passage_id": passage} for doc, passage in sorted(unread)],
            }
    elif result["status"] == "conflict":
        last_read = max(
            index for index, item in enumerate(observations)
            if item["action"] == "read" and item["ok"] and item["result"]["doc_id"] in cited_docs
        )
        if not any(item["action"] == "search" for item in observations[last_read + 1:]):
            return {
                "error": "冲突补查尚未执行。下一步使用 action=search，"
                         "query 由你根据当前问题写出，并包含适用范围、例外或优先级。"
            }
    elif result["status"] == "insufficient_evidence":
        searches = [item for item in observations if item["action"] == "search"]
        if len(searches) == 1 and searches[0]["ok"] and not searches[0]["result"]["hits"]:
            return {"error": "首轮检索为空。请用 action=search 改写主题词补搜，指代不明时可追问。"}
    return None


def run(model, knowledge, request, max_steps):
    observations = []
    trace = []
    evidence = {}
    discovered = set()
    result = None
    for step in range(1, max_steps + 1):
        entry = {"step": step}
        trace.append(entry)
        try:
            decision = model.decide(request, observations, max_steps - step + 1)
            if not isinstance(decision, dict):
                raise DecisionError("模型必须返回 JSON 对象")
            action = required_text(decision, "action", limit=30)
            entry.update(action=action, reason=required_text(decision, "reason", limit=200))
            if action not in {"search", "read", "finish"}:
                feedback = {
                    "ok": False,
                    "error": "动作名无效。action 只允许 search、read、finish。"
                             "若要报告工具失败，请用 action=finish 和 status=tool_error。",
                }
                entry["observation"] = feedback
                observations.append({"action": "validation", **feedback})
                continue
            if action == "finish":
                entry["args"] = {"status": decision.get("status"), "refs": decision.get("refs")}
                proposed = finish(decision, evidence, observations)
                review = review_completion(proposed, evidence, observations)
                if review:
                    feedback = {"ok": False, **review}
                    entry["observation"] = feedback
                    observations.append({"action": "validation", **feedback})
                    continue
                result = proposed
                entry["observation"] = {"ok": True, "status": result["status"]}
                break
            args = decision.get("args")
            if not isinstance(args, dict):
                raise DecisionError("工具参数必须是对象")
            if action == "search":
                limit = args.get("limit")
                if type(limit) is not int or not 1 <= limit <= 8:
                    raise DecisionError("检索条数须为 1 至 8 的整数")
                params = {"query": required_text(args, "query", limit=240), "limit": limit}
                tool = knowledge.search
            else:
                params = {
                    "doc_id": required_text(args, "doc_id", limit=40),
                    "passage_id": required_text(args, "passage_id", limit=40),
                }
                if (params["doc_id"], params["passage_id"]) not in discovered:
                    raise DecisionError("只能读取本轮检索找到的片段")
                tool = knowledge.read
            entry["args"] = params
            try:
                output = tool(**params)
                observation = {"ok": True, "result": output}
                if action == "search":
                    discovered.update(
                        (hit["doc_id"], passage_id)
                        for hit in output["hits"]
                        for passage_id in hit["passage_ids"]
                    )
                else:
                    evidence[(output["doc_id"], output["passage_id"])] = output
            except ToolError as error:
                observation = {"ok": False, "error": str(error)}
            entry["observation"] = observation
            observations.append({"action": action, "args": params, **observation})
        except DecisionError as error:
            entry["observation"] = {"ok": False, "error": str(error)}
            result = {
                "status": "model_error", "answer": "本次未能生成可靠答复。",
                "citations": [], "evidence_gap": str(error),
            }
            break

    if result is None:
        result = {
            "status": "step_limit", "answer": "已达到执行步数上限，本次未完成。",
            "citations": [], "evidence_gap": "尚未形成通过校验的最终答复。",
        }
    for index, entry in enumerate(trace):
        entry["next_action"] = (
            trace[index + 1].get("action", "model_error") if index + 1 < len(trace)
            else result["status"]
        )
    return {**result, "backend": model.label, "trace": trace}
