"""Local retrieval and verbatim passage reading."""

import json
import re
from pathlib import Path


DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "data" / "knowledge.json"


class ToolError(Exception):
    pass


def normalize(text):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.casefold())


class Knowledge:
    def __init__(self, path=DEFAULT_CORPUS, *, expand=True, fault=None):
        corpus = json.loads(Path(path).read_text(encoding="utf-8"))
        self.documents = {doc["doc_id"]: doc for doc in corpus["documents"]}
        self.aliases = corpus["aliases"] if expand else {}
        self.fault = fault

    def search(self, query, limit):
        if self.fault == "search":
            raise ToolError("检索服务暂不可用")
        query = normalize(query)
        ranked = []
        for doc_id, doc in self.documents.items():
            score = 0
            matches = []
            for term in doc["terms"]:
                if normalize(term) in query:
                    score += 3
                    matches.append(term)
                elif any(normalize(alias) in query for alias in self.aliases.get(term, [])):
                    score += 2
                    matches.append(term)
            if score:
                hit = {
                    "doc_id": doc_id, "title": doc["title"],
                    "version_date": doc["version_date"], "score": score,
                    "matched_terms": matches,
                    "passage_ids": [item["passage_id"] for item in doc["passages"]],
                }
                if "policy_topic" in doc:
                    hit["policy_topic"] = doc["policy_topic"]
                ranked.append(hit)
        ranked.sort(key=lambda hit: (-hit["score"], hit["doc_id"]))
        return {"hits": ranked[:limit], "total_hits": len(ranked)}

    def read(self, doc_id, passage_id):
        if self.fault == "read":
            raise ToolError("原文读取服务暂不可用")
        doc = self.documents.get(doc_id)
        if doc:
            for passage in doc["passages"]:
                if passage["passage_id"] == passage_id:
                    return {
                        "doc_id": doc_id, "title": doc["title"],
                        "version_date": doc["version_date"], **passage,
                    }
        raise ToolError("指定片段不存在")
