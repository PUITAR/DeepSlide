通过引入“全局节奏策略（Global Pacing Strategy）”解决了逻辑节点内容完整性与时间限制之间的矛盾：

1. 全局规划 Prompt ：
   
   - 在 System Prompt 中新增了 CRITICAL 级别的节奏策略说明。
   - 明确告知 Agent 必须进行 事前规划 ，并根据时间预算（例如 300秒 ≈ 5-7页）动态调整每页的信息密度。
   - 确立了 Completeness > Detail （完整性优于细节）的原则：如果内容多时间少，必须压缩每一页的细节，而不是生成一半后被截断。
2. 实时进度反馈 ：
   
   - 在每一步的交互中，不仅告知 Agent 已用时间，还明确显示 剩余时间 。
   - 加入动态提醒：“If you are halfway through the time, you should be halfway through the content.”（如果你用了一半的时间，你的内容进度也应该到一半），迫使 Agent 实时校准生成节奏。
现在，Agent 会像人类演讲者一样，根据剩余时间动态调整语速和内容深度，确保在规定时间内讲完所有关键点。