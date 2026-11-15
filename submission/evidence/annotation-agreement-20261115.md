# LiCoEval 47 条正例 · 双人独立标注一致性复核

- 生成时间：2026-11-15T06:30:42Z
- 复现命令：`python scripts/eval_annotation_agreement.py`
- 数据源：两份独立盲标 CSV（未修改任何标签）+ 第三人复核 CSV；固定种子 20261115，2000 次百分位 bootstrap。

> **口径说明**：本文件只衡量**两名标注人是否按同一口径打标**（评分者间信度），不衡量标签本身是否正确。正确性仍由逐字命中 / 覆盖率证据与第三人复核支撑，不得把高 AC1 写成「47/47 已证实为法律意义上的复制」。

## 一、2×2 混淆矩阵（A = 实质逐字复现；非 A = B/C）

| 标注人1 ＼ 标注人2 | A | 非 A | 合计 |
|---|---|---|---|
| A | 44 | 1 | 45 |
| 非 A | 2 | 0 | 2 |
| 合计 | 46 | 1 | 47 |

标注人1 分布 A 45 / B 2 / C 0；标注人2 分布 A 46 / B 1 / C 0。

## 二、一致性指标（同一批 47 条，无重标、无改标签）

| 指标 | 数值 | 95% bootstrap CI | 含义 |
|---|---|---|---|
| 原始一致率 po | 0.9362 | [0.8511, 1.0] | 44 / 47 条两人给出同一标签 |
| Cohen's κ（3 类） | -0.0292 | [-0.0682, 0.0] | 受 prevalance 偏斜影响，**出现 kappa 悖论** |
| PABAK（2×2） | 0.8723 | [0.7021, 1.0] |  prevalence-adjusted bias-adjusted kappa |
| Gwet's AC1（2×2） | 0.932 | [0.8273, 1.0] | 对高 prevalance 稳健，为本组主报告指标 |

期望一致率：Cohen pe = 0.938；Gwet pe = 0.0618；A 类平均边际 prevalance π = 0.9681。

## 三、为什么 κ 是负的（kappa 悖论）

1. 47 条是 LiCoEval 按 striking-similar **预先筛出的正例**，两名标注人几乎全判 A（45 / 47 与 46 / 47），类别分布极端偏斜。
2. 此时「随机也大概率都判 A」，Cohen 的期望一致率 pe 高达 0.938，甚至略高于实际一致率 0.9362，于是 κ=(po−pe)/(1−pe) 落在 0 以下。这是 1990 年 Feinstein & Cicchetti 描述的**high-agreement / low-kappa paradox**，不是两人随机乱标。
3. 对照：把同一混淆矩阵换成对 prevalance 稳健的系数，PABAK = 0.8723、Gwet's AC1 = 0.932，均属「几乎完全一致」。两者与 po 一起报告，不再单独引用 κ。
4. κ 的 bootstrap CI [-0.0682, 0.0] 跨 0，说明在 n=47 且偏斜的前提下 κ **本身不可估计**；这不是一致性的证据，而是「该系数不适用」的证据。

## 四、分歧闭环与最终标签

- 分歧 3 条（人1 A / 人2 B 或相反），全部交第三人按逐字 token 数与片段覆盖率复核，复核记录见 `model-leak-20261021-复核.csv`。
- 复核后最终标签 A = 47 / 47；复核结论与两名标注人原始标签的合并一致率按「最终标签」口径记为 100%（即所有分歧已闭环），**这不等于原始盲标一致率**，两者不可混写。
- 报告表述建议：「两名成员独立盲标一致 0.9362（44/47）；受类别高度偏斜影响，Cohen's κ=-0.0292（kappa 悖论，不适用），改用 Gwet's AC1=0.932、PABAK=0.8723；3 条分歧经第三人复核闭环，最终独立确认 A 47/47。」

## 五、局限

- n=47， bootstrap CI 仍偏宽；标注人未受正式版权法培训，B/C 边界依赖第三人复核。
- 样本是论文预筛的 striking-similar 正例，不是模型全部输出；本表不衡量召回率或误报率。
- 以上系数均为评分者间信度指标，不构成对「复制」的法律判断。

## 六、参考文献

[1] Feinstein AR, Cicchetti DV. High agreement but low kappa: I. The problems of two paradoxes. J Clin Epidemiol. 1990;43(6):543-549.  [2] Byrt T, Bishop J, Carlin JB. Bias, prevalence and kappa. J Clin Epidemiol. 1993;46(5):423-431.  [3] Gwet KL. Computing inter-rater reliability and its variance in the presence of high agreement. Br J Math Stat Psychol. 2008;61(1):29-48.
