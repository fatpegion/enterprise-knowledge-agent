"""JSON-in/JSON-out CLI."""

import argparse
import json
import sys
from pathlib import Path

from .agent import run
from .knowledge import DEFAULT_CORPUS, Knowledge
from .models import ChatModel, MockModel


def load_request(path):
    request = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(request, dict):
        raise ValueError("输入须为 JSON 对象")
    question = request.get("question")
    history = request.get("history", [])
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise ValueError("question 须为 1 至 500 字符")
    if not isinstance(history, list) or len(history) > 8:
        raise ValueError("history 须为不超过 8 条消息的数组")
    for item in history:
        if (
            not isinstance(item, dict) or item.get("role") not in ("user", "assistant")
            or not isinstance(item.get("content"), str) or not 1 <= len(item["content"].strip()) <= 500
        ):
            raise ValueError("每条 history 需要 user 或 assistant 角色与 1 至 500 字符的 content")
    return {
        "question": question.strip(),
        "history": [{"role": item["role"], "content": item["content"]} for item in history],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mode", choices=("mock", "live"), required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--fault", choices=("search", "read"), help="测试工具故障")
    parser.add_argument("--no-aliases", action="store_true", help="检索基线对照")
    parser.add_argument("--output", type=Path, help="以 UTF-8 写入结果文件")
    options = parser.parse_args(argv)
    if not 1 <= options.max_steps <= 24:
        parser.error("--max-steps 须在 1 至 24 之间")
    try:
        request = load_request(options.input)
        knowledge = Knowledge(options.corpus, expand=not options.no_aliases, fault=options.fault)
        model = ChatModel() if options.mode == "live" else MockModel()
        result = run(model, knowledge, request, options.max_steps)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if options.output:
            options.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.buffer.write(rendered.encode("utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"输入、配置或资料错误：{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
