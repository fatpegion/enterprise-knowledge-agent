"""Compare the first retrieval call with and without configured aliases."""

import json
from pathlib import Path

from src.knowledge import Knowledge


QUERIES = [
    ("访客网络怎么接入？", ["D03"]),
    ("来客上网的访问码怎么办？", ["D03"]),
    ("外来人员连无线要向谁申请？", ["D03"]),
    ("我垫付款最晚什么时候申报？", ["D01", "D02"]),
    ("专业版保存成片有没有角标？", ["D05"]),
    ("公司有没有宠物保险？", []),
    ("多久才能预约会议室？", []),
]


def main():
    variants = {"baseline": Knowledge(expand=False), "aliases": Knowledge()}
    summary = {name: 0 for name in variants}
    rows = []
    for query, expected in QUERIES:
        row = {"query": query, "expected_top_ids": expected}
        for name, knowledge in variants.items():
            result = knowledge.search(query, 5)
            actual = [hit["doc_id"] for hit in result["hits"]]
            match = actual[:len(expected)] == expected if expected else not actual
            row[name] = {"match": match, **result}
            summary[name] += int(match)
        rows.append(row)
    report = {"count": len(rows), "matches": summary, "cases": rows}
    output = Path(__file__).with_name("retrieval-comparison.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
