"""Run the CLI against the acceptance inputs and save fresh outputs with traces."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
CASES = {
    "normal": ("normal", [], "answered", {"D03"}, ("Guest-WiFi", "访问码")),
    "conflict": ("conflict", [], "conflict", {"D01", "D02"}, ("30", "15", "确认")),
    "missing": ("missing", [], "insufficient_evidence", set(), ()),
    "paraphrase": ("paraphrase", [], "answered", {"D03"}, ("访问码",)),
    "followup": ("followup", [], "answered", {"D04"}, ("基础版", "1080")),
    "tool-failure": ("tool-failure", ["--fault", "search"], "tool_error", set(), ()),
    "read-failure": ("tool-failure", ["--fault", "read"], "tool_error", set(), ()),
    "step-limit": ("normal", ["--max-steps", "1"], "step_limit", set(), ()),
    "revised": ("conflict", ["--corpus", str(HERE / "revised.corpus.json")], "answered",
                {"D01"}, ("45",)),
}


def checks(name, output, status, cited, words):
    trace = output["trace"]
    citations = output["citations"]
    reads = [
        item["observation"]["result"] for item in trace
        if item.get("action") == "read" and item["observation"]["ok"]
    ]
    assert output["status"] == status, f"期望 {status}，得到 {output['status']}"
    assert {item["doc_id"] for item in citations} == cited, "引用文档集合不符"
    assert all(item in reads for item in citations), "引用未逐字来自本轮读取"
    assert all(word in output["answer"] for word in words), "答案缺少关键信息"
    assert bool(output["evidence_gap"]) == (status != "answered"), "资料缺口不符"
    if name == "conflict":
        last_read = max(index for index, item in enumerate(trace) if item["action"] == "read")
        assert any(item["action"] == "search" for item in trace[last_read + 1:]), "缺少冲突后补查"
    if name in {"tool-failure", "read-failure"}:
        action = "search" if name == "tool-failure" else "read"
        assert any(item["action"] == action and not item["observation"]["ok"] for item in trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), required=True)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    out = args.output_dir or HERE / args.mode
    out.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in args.case or CASES:
        source, flags, status, cited, words = CASES[name]
        path = out / f"{name}.output.json"
        proc = subprocess.run([
            sys.executable, "-m", "src.main", "--mode", args.mode,
            "--input", str(HERE / f"{source}.input.json"), "--output", str(path), *flags,
        ], cwd=HERE.parent, check=False)
        try:
            if proc.returncode:
                raise AssertionError(f"CLI 退出码 {proc.returncode}")
            output = json.loads(path.read_text(encoding="utf-8"))
            checks(name, output, status, cited, words)
            print(f"PASS {name}: {output['status']} ({len(output['trace'])} steps)", flush=True)
        except AssertionError as error:
            failed.append(name)
            print(f"FAIL {name}: {error}", flush=True)
    print(f"Failed: {', '.join(failed) or 'none'}", flush=True)
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
