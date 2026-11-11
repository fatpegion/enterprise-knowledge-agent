# 评估

在 Windows、Python 3.9.13 执行 `python -m unittest discover -s tests -v`，15 项通过，见 [单元测试日志](../examples/test-results.txt)。运行 `python -m examples.run_suite --mode mock`，9 组离线 CLI 验收通过，见 [Mock 验收日志](../examples/mock-results.txt)。HTTP 适配的单元测试使用受控响应，检查检索与读取观察确实发回给模型接口。

| 场景 | 输入 | 期望与离线结果 |
| --- | --- | --- |
| 明确答案 | [正常输入](../examples/normal.input.json) | 引用 D03，给出访客 Wi-Fi 与访问码步骤。[实际输出与 Trace](../examples/mock/normal.output.json) |
| 文档冲突 | [冲突输入](../examples/conflict.input.json) | 读两份制度再补查，列出 30 天与 15 天，请求确认。[实际输出与 Trace](../examples/mock/conflict.output.json) |
| 资料外问题 | [缺资料输入](../examples/missing.input.json) | 首次无候选后改写检索，仍无候选时返回资料不足。[实际输出与 Trace](../examples/mock/missing.output.json) |
| 相似改写 | [改写输入](../examples/paraphrase.input.json) | 「来客上网」命中 D03。[实际输出与 Trace](../examples/mock/paraphrase.output.json) |
| 上下文追问 | [历史输入](../examples/followup.input.json) | 根据前文定位基础版视频导出，引用 D04 给出 1080p。[实际输出与 Trace](../examples/mock/followup.output.json) |
| 检索失败 | [故障输入](../examples/tool-failure.input.json) 加 `--fault search` | 观察检索失败后结束，无引用。[实际输出与 Trace](../examples/mock/tool-failure.output.json) |
| 原文读取失败 | 同一输入加 `--fault read` | 检索命中但未取得原文，返回工具失败。[实际输出与 Trace](../examples/mock/read-failure.output.json) |
| 达到预算 | 正常输入加 `--max-steps 1` | 只执行一次检索，返回明确的未完成状态。[实际输出与 Trace](../examples/mock/step-limit.output.json) |
| 替换资料 | 冲突输入加 `--corpus examples/revised.corpus.json` | D01 改为 45 天，移除 D02。读一条即得到 45 天。[替换资料](../examples/revised.corpus.json) · [实际输出与 Trace](../examples/mock/revised.output.json) |

## 检索对照

执行 `python -m examples.compare_retrieval`，用同一批查询比较标准词检索和同义词扩展。7 条查询包含 1 条标准问法、4 条改写和 2 条资料外问题。标准词基线有 3 条符合预期，扩展后 7 条符合预期。「来客上网的访问码怎么办？」由零结果变为 D03 排首位，得分 2。两个资料外问题在两种模式均为零结果。标签按本合成知识库人工指定。[原始对照结果](../examples/retrieval-comparison.json)

## 真实模型首次试跑

Qwen2.5-1.5B-Instruct Q4_K_M 的 9 组场景均返回 `model_error`。访客网络用例在命中并读取 D03 后重复读取，随后缺少必填的动作依据。冲突用例尝试在检索前直接读取文档，被执行器拒绝。这个结果促使复测改用更强的指令模型。[首次日志](../examples/live-qwen25-initial/live-results.txt) · [访客网络 Trace](../examples/live-qwen25-initial/normal.output.json) · [冲突 Trace](../examples/live-qwen25-initial/conflict.output.json)

Qwen3-4B-Instruct-2507 Q4_K_M 用同一版提示词试跑时通过 5/9。冲突与资料外问题缺少面向用户的回复字段，两种故障把状态名误填为动作。随后在提示词中明确动作枚举，增加非成功状态的 JSON 示例，并要求识别冲突后先补查再结束。[4B 初版日志](../examples/live-qwen3-initial/live-results.txt) · [4B 初版失败 Trace](../examples/live-qwen3-initial)

调整提示词后通过 7/9。冲突用例只读了 D01，便将 30 天当作确定答案。检索故障用例再次把状态名写进动作字段。随后在执行器增加同等或更高分候选的覆盖校验、冲突补查校验，以及预算内的模型纠错反馈。[第二版日志](../examples/live-qwen3-v2/live-results.txt) · [第二版错误作答 Trace](../examples/live-qwen3-v2/conflict.output.json)

加入校验后通过 7/9。报销用例补读了 D02 并识别冲突，仍重复提交结论，最终达到上限。导出追问因两个 FAQ 同分触发补读，模型把分辨率和水印误判为冲突。随后将覆盖校验缩小到显式标记的同一制度事项，并把校验原因放在模型输入末尾，明确提示模型生成下一步。[第三版日志](../examples/live-qwen3-v3/live-results.txt) · [冲突 Trace](../examples/live-qwen3-v3/conflict.output.json) · [追问 Trace](../examples/live-qwen3-v3/followup.output.json)

## 最终真实模型执行

最终 9/9 组通过，覆盖六项必验场景，以及原文读取故障、执行步数上限和资料替换。一次批量复测中，模型正确解释了冲突，但只说「需进一步明确」，缺少明确的确认请求。加入固定的用户确认提示后，单独复跑冲突，并用相同断言核验九组最终输出。运行环境为 Windows、Python 3.9.13、Node.js 24.15.0、node-llama-cpp 3.22.3、CPU 6 线程、上下文长度 8192。权重为 Qwen3-4B-Instruct-2507 Q4_K_M，已核对发布方 SHA256。[复跑命令](../README.md) · [批量运行日志](../examples/live-batch-results.txt) · [冲突定向复跑日志](../examples/live-conflict-rerun.txt) · [最终输出校验](../examples/live-results.txt) · [完整输出与 Trace](../examples/live)

- 访客网络检索命中 D03，模型读取原文后结束，给出连接 Guest-WiFi 与申请当日访问码的步骤。[正常 Trace](../examples/live/normal.output.json)
- 报销检索命中同一事项的 D01 与 D02。首次拟作答因 D02 未读被退回。模型补读 D02，识别冲突后按反馈发起针对适用范围、优先级和例外的检索。缺少明确优先规则时，两份文档原样引用，并请员工确认。[冲突 Trace](../examples/live/conflict.output.json)
- 追问通过历史确定产品版本和功能，引用 D04 给出基础版 1080p。[追问 Trace](../examples/live/followup.output.json)
- 资料外问题的空结果只说明当前知识库覆盖不足。人工复核发现模型曾把这个结论扩展到公司层面，最终版对资料不足回复使用限定范围的措辞，并要求对首轮空结果补搜或追问。[资料不足 Trace](../examples/live/missing.output.json)
- 同一报销问题换用新版资料后，只命中 45 天的 D01。模型读取新版原文后直接作答。[替换资料 Trace](../examples/live/revised.output.json)

## 验证边界

Mock 的行为由确定性规则驱动，能验证执行器流程和失败处理。真实模型效果以 live 记录为准。检查器要求引用逐字来自当前执行的读取结果。语义支持仍依赖模型判断与样例核查。语料规模为五份合成文档，同义词表覆盖有限。检索对照是针对配置词表的合成回归检查，尚未验证大语料和未见表达的稳定性。
