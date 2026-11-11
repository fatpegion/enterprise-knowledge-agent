# 企业知识问答 Agent

输入员工问题和可选对话历史，返回回答、文档 ID、版本日期、逐字原文、资料缺口、任务状态和执行 Trace。合成知识库包含报销制度、访客网络和视频导出 FAQ。

## 快速运行

需要 Python 3.9+。项目只用标准库。进入仓库根目录运行以下命令。

```bash
python -m src.main --mode mock --input examples/normal.input.json
python -m src.main --mode mock --input examples/conflict.input.json
python -m src.main --mode mock --input examples/tool-failure.input.json --fault search
python -m unittest discover -s tests -v
python -m examples.run_suite --mode mock
```

Mock 无需配置，用于验证流程、引用校验和异常处理。真实模型决策使用 `--mode live`。

## 真实模型

准备支持 Chat Completions 和 `response_format: json_object` 的服务。下面用 Node.js 24 和 `node-llama-cpp` 3.22.3 启动本地 CPU 推理服务，使用 [Qwen3-4B-Instruct-2507 的 Q4_K_M 权重](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/blob/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf)。

```powershell
$agentRuntime = Join-Path $env:TEMP 'enterprise-qa-runtime'
New-Item -ItemType Directory -Force $agentRuntime | Out-Null
npm.cmd install --prefix $agentRuntime --ignore-scripts --no-audit --no-fund node-llama-cpp@3.22.3
Copy-Item examples/local_model_server.mjs $agentRuntime -Force
$agentWeights = Join-Path $agentRuntime 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
curl.exe -fL 'https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf' -o $agentWeights
node (Join-Path $agentRuntime 'local_model_server.mjs') $agentWeights 8080
```

保持推理服务运行，在另一终端的仓库根目录执行。

```powershell
$env:MODEL_BASE_URL = 'http://127.0.0.1:8080/v1'
$env:MODEL_NAME = 'qwen3-4b-instruct-2507-q4_k_m'
python -m src.main --mode live --input examples/conflict.input.json
python -m examples.run_suite --mode live
```

远程服务须按供应商配置模型名、基础 URL 和进程环境中的 `MODEL_API_KEY`。配置示例见 [.env.example](.env.example)。CLI 读取进程环境。远程模式会把问题、历史和已观察到的合成文档内容发送给模型服务。

## 评审入口

| 检查内容 | 文件 |
| --- | --- |
| 用户、范围和六项验收 | [需求](docs/01-requirements.md) |
| 模型与工具如何交互 | [方案](docs/02-solution.md) |
| 用例、实跑结果与限制 | [评估](docs/03-evaluation.md) |
| AI 辅助和候选人贡献 | [AI 使用记录](docs/04-ai-usage.md) |
| 用时、复盘和下一步 | [复盘](docs/05-retrospective.md) |
| 版本化合成资料 | [知识库](data/knowledge.json) |

输入示例见 [examples](examples/)。每个实际输出文件内嵌 `trace`，包含动作、参数、工具结果、下一动作及简短依据。默认最多执行 10 步，含最终结束动作。达到上限返回 `step_limit`。业务状态通过 JSON 返回，输入、配置或文件错误以退出码 2 表示。批量验收有失败时返回非零退出码。

可用以下命令复现替换资料与步数上限。替换资料保留 D01、更新为 45 天，并移除 D02。

```bash
python -m src.main --mode mock --input examples/conflict.input.json --corpus examples/revised.corpus.json
python -m src.main --mode mock --input examples/normal.input.json --max-steps 1
```

所选题目为「企业知识问答 Agent」。提交时按考核方原始题单填写数字题号，并使用 `git rev-parse HEAD` 获取最终 commit SHA。目录结构参考考核方提供的 [交付示例](https://github.com/lwz1357/agent-campus-submission-example)。
