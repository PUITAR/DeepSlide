---
title: Evaluation Metrics
author: Yangming
---

# 整体说明

结合20251213的讨论，讨论内容如下：

> 好的PPT应该长什么样？
> - 针对不同的对象：有重点，一目了然，逻辑清晰，不要有多余废话的 
> - 不同的对象评测的侧重点不同（列举3～5个对象）
> 
> 按照做短视频的思路做PPT，PPT要怎么像短视频一样抓人眼球：
> - 爆点/吸引人的点：
> - 起承转合
> - 节奏
> 
> 短视频是怎么吸引眼球的：
> link（从9:25开始）: https://www.bilibili.com/video/BV1itK3zsEx2/
> - 强烈的对比和冲突封面，吸引观众（骗进来）
> - 平均播放时长/百分比（留住看你的视屏）
>     - 比长视频更容易吸引人的是短视频：节奏快、内容新颖、话题精简
>     - 比短视频更容易吸引人的是把很多短视频塞在一起的长视频（一堆梗）：具备短视频的有点，同时甚至不需要滑动
> 
> PPT是一个“长视频”，那么我们应该怎么做？
> - 一个吸引人的“引入”，增加抬头率（爆点）
> - 不停的“转换”，使观众保持关注，增加留存率（节奏）
> - 转换的方式=起承转合

我们总结出好的Presentation应该具备的2大法则：
- 吸引力法则（借鉴短视频等流媒体制作的一些哲学）
- 可靠性法则（传统DOC2PPT关注的要素）

吸引力法则强调材料对读者的吸引力，主要在于怎么能够更引人入胜，更好留住听众的注意力；可靠性法则在于怎么更全/更准地帮助演讲者表达内容，更稳定地编译出材料；审美法则则在于怎么能够更符合人类审美标准，更符合听众的expectation。在接下来的材料中，我们将Slide看成是一个内容帧序列$\mathcal{F}=\{f_1, f_2, \cdots, f_n\}$，每个Slide都包含了演讲者要展示的内容帧；将演讲稿看成是一个文本段落序列
$\mathcal{P}=\{p_1, p_2, \cdots, p_m\}$，每个段落都包含了演讲者要演说的台词，其中$|\mathcal{F}|=|\mathcal{P}|=n$。

# 吸引力法则
## Open Hook Score, OHS
早期钩子（Open Hook）是指在演讲开始时，通过一个简单的问题或话题，引发听众的兴趣和关注。这个问题或话题可以是关于演讲者的个人背景、演讲的主题、或演讲者的专业经历等。早期钩子的作用是为了吸引听众的注意力，使他们更愿意参与到演讲中。在我们的设计中，模型主要捕捉以下要点进行钩子分数的计算：
- 是否明确问题/话题/矛盾/痛点
- 是否具备引人入胜的例子或反常的情况
- 是否能直接让听众明白自己为什么要听
- ...

捕捉要点被看成是一个规则集合$\mathcal{R}_{OHS}$，每个规则都对应了一个$r_i$，其中$i$表示第$i$个规则。输入Slide和演讲稿序列，以及早期下标$m \leq n$（表示前$m$个元素），OHS的计算如下：

$$
OHS(\mathcal{F}, \mathcal{P}, m) = \sum_{k=1}^{m}\sum_{i=1}^{|\mathcal{R}_{OHS}|} \alpha_i \mathbb{I}_{r_i}(f_k, p_k),
$$
其中$\alpha_i$表示第$i$个规则的权重，且$\sum_{i=1}^{|\mathcal{R}|} \alpha_i = 1$。$\mathbb{I}_{r_i}(f_m, p_m)$表示第$i$个规则是否对Slide和演讲稿序列的第$m$个元素生效。如果第$i$个规则对第$m$个元素生效，那么$\mathbb{I}_{r_i}(f_m, p_m)=1$；否则，$\mathbb{I}_{r_i}(f_m, p_m)=0$。示性函数可以用LLM进行判别。

## Retention Score, RS
留存分数（Retention Score）是指在演讲过程中，听众是否能够保持关注和参与。我们认为好的演讲应该具备以下几方面的良好特征：
- 整个演讲过程的持续刺激（整体）
- 演讲过程避免某个阶段的平铺直叙（局部）
- 良好的演讲节奏（动态过程）

给定刺激判别规则集合$\mathcal{R}_{RS}$，例如
- 具有演讲者个人观点/定位/实例
- 具有提问/换位思考？
- ...

只要满足其中任意一个规则，就认为该段落是一个刺激段落。

刺激频率 **Stimulus Frequency (SF)** 是指在演讲过程中，整个演讲过程中，出现的刺激次数。它从整体上衡量了演讲者在整个过程中，是否能够持续地给听众带来刺激。

$$
SF(\mathcal{F}, \mathcal{P}) = \sum_{k=1}^{n} \mathbb{I}\!\left(\sum_{i=1}^{|\mathcal{R}_{RS}|} \mathbb{I}_{r_i}(f_k, p_k) > 0\right).
$$

最大平淡度 **Maximal Plainness (MP)** 是指在演讲过程中，整个演讲过程中，出现的最大连续 _plain_ 段落数。它从局部上衡量了演讲者在整个过程中，是否能够避免某个阶段的平铺直叙。
$$
MP(\mathcal{F}, \mathcal{P}) = \max_{1 \leq i \leq n} \sum_{k=i}^{n} \mathbb{I}\!\left(\sum_{i=1}^{|\mathcal{R}_{RS}|} \mathbb{I}_{r_i}(f_k, p_k) = 0\right).
$$

节奏分数 **Rhythm Rate (RR)** 用于评估演讲过程的节奏。它从动态角度衡量演讲者能否在整个过程中保持良好的节奏。有吸引力的演讲，其刺激分布并非一条直线，而是有规律的“波浪”。刺激往往导致内容忠诚度下降，即偏离原材料，因此刺激与平淡应相随出现。

RR 旨在衡量实际刺激序列 $\{S_1, S_2, \dots, S_n\}$（$S_k=1$ 表示刺激段，$S_k=0$ 表示平淡段）与理想周期性交替模式的契合程度。我们采用自相关函数 $\rho(L)$ 来量化这种周期性与交替性。

1. 实际刺激序列 $S_k$  
   $$
   S_k = \mathbb{I}\!\left(\sum_{i=1}^{|\mathcal{R}_{RS}|} \mathbb{I}_{r_i}(f_k, p_k) > 0\right)
   $$  
   $\bar{S}$ 为序列平均刺激强度，$\bar{S} = \frac{1}{n}\sum_{k=1}^{n} S_k$。

2. 自相关函数 $\rho(L)$  
   $$
   \rho(L) = \frac{\sum_{k=1}^{n-L} (S_k - \bar{S}) (S_{k+L} - \bar{S})}{\sum_{k=1}^{n} (S_k - \bar{S})^2}
   $$

3. 节奏分数 RR 公式  
   RR 奖励理想周期 $T=2$ 上的高相关性 $\rho(2)$，同时惩罚相邻段落的连续性 $\rho(1)$ 接近 $+1$（即平铺直叙）。  
   $$
   RR(\mathcal{F}, \mathcal{P}) = \frac{1}{2} \left[ \frac{\rho(2) + 1}{2} + \frac{1 - \rho(1)}{2} \right]
   $$  
   - 第一项 $\frac{\rho(2) + 1}{2}$：奖励周期性。$\rho(2)=1$ 时该项为 1（完美周期）。  
   - 第二项 $\frac{1 - \rho(1)}{2}$：奖励交替性/惩罚连续性。$\rho(1)=-1$ 时该项为 1（完美交替）；$\rho(1)=1$（完全连续）时该项为 0。

最终，整体的RR分数是SF和MP的加权平均：
$$
RS = w_{SF} \cdot SF + w_{MP} \cdot (1 - MP) + w_{RR} \cdot RR
$$

## Cognitive Load Control Score, CLC
除了考虑能够刺激听众、留存注意力之外，还需要考虑到演讲者的认知负载是否过高。如果认知负载过高，会导致听众注意力分散，从而影响演讲的效果。我们认为认知负载的控制应该从两个角度出发：(1) 单位时间信息量的控制; (2) 逻辑的控制。

- 单位时间接收过多的信息可能让听众无法理解，从而导致注意力分散。因此，我们需要控制单位时间内接收的信息量，确保不会超过听众的处理能力（知识点凝聚程度）。

- 演讲要点之间彼此之间的关联关系能够降低听众理解的成本，例如当用户讲到实验章节时，回顾算法的某个设计细节，或许能够帮助用户理解实验设计的初衷（知识点关联图谱）。


认知负载控制分数 (Cognitive Load Control Score, CLC)认知负载控制分数 CLC 衡量演讲者在组织逻辑结构时，能否通过有效的回顾/预示（"call"关系）来提供脚手架 (Scaffolding)，从而减轻听众理解新信息的负担。您的算法提供了一份知识点之间的关系图谱 $G=(V, E)$，其中 $V=\{v_1, v_2, \dots, v_n\}$ 是知识点序列，$E$ 是“call”关系集合。

1. 量化指标：知识连贯性 (Knowledge Coherence, KC)知识连贯性 KC 旨在评估知识点引用是否具有高局部凝聚度和低时间跨度。A. 平均引用跨度 (Average Reference Span, ARS)ARS 衡量知识点引用之间的平均时间距离。跨度越大，听众回顾的负担越重，认知负载越高。
    $$
    ARS = \frac{1}{|E|} \sum_{(v_k, v_j) \in E} |k - j|
    $$

    其中，$v_k$ 是发出 "call" 的知识点，$v_j$ 是被引用的知识点。$|E|$ 是总的 "call" 关系数量。$|k - j|$ 是知识点在演讲序列中的索引距离。B. 局部凝聚比例 (Local Cohesion Ratio, LCR)LCR 衡量“call”关系集中在预设局部窗口 $W$ 内的比例。高 LCR 表示演讲组织结构紧凑、局部连贯性强。通常 $W$ 取一个较小的整数，如 $W=3$ 或 $W=5$。
    $$
    LCR = \frac{1}{|E|} \sum_{(v_k, v_j) \in E} \mathbb{I}(|k - j| \leq W)
    $$

2. CLC 公式CLC 分数将 LCR 作为奖励项（奖励局部性），将 ARS（平均跨度）作为惩罚项。为了将分数归一化到 $[0, 1]$ 范围，并平衡贡献，我们使用归一化形式。首先，对 ARS 进行归一化，假设最大可能跨度为 $n-1$：
    $$
    ARS_{norm} = \frac{ARS}{n-1}
    $$
    
    然后，定义 CLC 为局部凝聚比例和 **平均引用跨度（的取反）** 的加权平均：
    $$
    CLC(\mathcal{F}, \mathcal{P}, G) = \frac{w_{LCR} \cdot LCR + w_{ARS} \cdot (1 - ARS_{norm})}{w_{LCR} + w_{ARS}}
    $$
    $w_{LCR}$ 和 $w_{ARS}$ 是权重，可以设置为相等（例如 $w_{LCR} = w_{ARS} = 0.5$）以给予两者同等重要性，此时公式简化为：
    $$
    CLC = \frac{LCR + (1 - ARS_{norm})}{2}
    $$

# 可靠性法则
 
可靠性法则关注演讲材料（包括 Slide 和讲稿）在生成和交付过程中的稳定性和准确性，确保演讲者能够稳定、准确地表达其内容。
1. 系统稳定度 (System Stability)该指标衡量从原始文档到最终演讲材料（幻灯片、讲稿）的自动编译或生成过程的可靠性。定义： 系统稳定度通常通过衡量系统在重复操作下产生可用输出的频率来体现。在您的框架中，我们将其定义为平均编译通过次数（或成功率）。背景： 您的 DOC2PPT/生成系统可能涉及复杂的流程（如文本分段、关键词提取、图像生成、布局排版）。每一次尝试生成一套完整的演讲材料，即为一次“编译”。如果编译频繁失败（例如，因为生成模型崩溃、排版冲突或安全审查不通过），则系统稳定度低。量化指标： 平均编译通过成功率 (Average Compilation Success Rate, ACSR)
    $$
    ACSR = \frac{\text{成功生成完整且可用材料的次数}}{\text{总尝试生成次数}}
    $$
    高 ACSR 意味着演讲者可以信赖系统稳定地提供可用的材料，减少手动干预和重试成本，是传统软件工程中“可用性”的体现。

2. 文本忠诚度 (Textual Fidelity)
    文本忠诚度量化了生成的 Slide/Speech 序列 $\mathcal{F}$ 和 $\mathcal{P}$ 相对于原始文档知识帧 $\mathcal{T}$ 的匹配程度。假设 $|\mathcal{F}| = |\mathcal{P}| = |\mathcal{T}| = n$，其中 $p_k$ 是生成的第 $k$ 个演讲段落， $t_k$ 是原始文档对应的第 $k$ 个知识帧内容。
    - ROUGE 分数 (Recall-Oriented Understudy for Gisting Evaluation)ROUGE 衡量生成的文本（$p_k$）与参考文本（$t_k$）之间重叠的单位（n-gram）数量。高 ROUGE 分数通常表示召回率高，即生成内容覆盖了原始文档的关键信息。其中 $F_{ROUGE}$ 是 ROUGE-1, ROUGE-2, ROUGE-L 的平均值。
        $$
        F_{ROUGE}(\mathcal{F}, \mathcal{P}, \mathcal{T}) = \frac{1}{n} \sum_{k=1}^{n} (\text{ROUGE}(p_k, t_k) + \text{ROUGE}(f_k, t_k))
        $$
        其中，$\text{ROUGE-N}(p_k, t_k)$ 是第 $k$ 帧生成段落和知识帧的 ROUGE-N 值。常用的有 ROUGE-1 (Unigram)、ROUGE-2 (Bigram) 和 ROUGE-L (最长公共子序列)。
    
    - BERTScoreBERTScore 利用 BERT 等预训练的语言模型嵌入（Embeddings）来计算生成文本和参考文本之间的语义相似度，它比 ROUGE 更关注语义而非精确的词重叠。平均 BERTScore 忠诚度分数 ($F_{BERT}$)
        $$
        F_{BERT}(\mathcal{F},\mathcal{P}, \mathcal{T}) = \frac{1}{n} \sum_{k=1}^{n} (\text{BERT}(p_k, t_k) + \text{BERT}(f_k, t_k))
        $$
        
    综合文本忠诚度分数 ($F_{Text}$)最终的文本忠诚度分数可以由这些指标加权平均得出：
    $$
    F_{Text} = w_{ROUGE} \cdot F_{ROUGE\_Avg} + w_{BERT} \cdot F_{BERTScore}
    $$

    NOTE: BERTScore/Rouge调包计算即可。

    参考：Knowledge-Centric Templatic Views of Documents

3. 图片忠诚度 (Visual Fidelity)：图像比例 (Figure Proportion)，衡量源文档中相关图像被成功包含在最终演示文稿中的比例。这是一个重要的指标，因为它确保了多模态输入的有效利用。

    参考：PreGenie: An Agentic Framework for High-quality Visual Presentation Generation


# 人工标注

以上均为自动化/LLM驱动的PPT量化指标。最好同样提供人工标注的评估准则。
<font color="red">[TODO: 考虑在后续开源后搭建在线DEMO演示站点，让其他人在浏览过程中顺便标注评分]</font>

# 对象评审

PPT针对不同的对象，会有不同的评测结果，GDPeval可以对不同的对象进行评测，可以借鉴一下。