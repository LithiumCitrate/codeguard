# 真实模型泄漏正例标注表（双人独立标注）

> **状态（2026-10-25）**：双人独立标注与第三人复核**已完成**。一致 44/47（93.6%），
> Cohen's κ=-0.0292（一方几乎全 A 造成的分布偏斜），3 条分歧由队长艾倏然复核为 A，
> 最终独立确认 A 47/47。原始记录见 `-标注人1.csv` / `-标注人2.csv` / `-复核.csv`，
> 合并结果见 `-标注汇总.md`。下表"标注1/标注2"两列由汇总回填，仅作人读总表。

来源：LiCoEval（ICSE 2025，AGPL-3.0-or-later）公布的 GPT-4o 真实生成代码，以及论文判定与之 striking-similar 的开源原文。本表只列摘要与指标，不含第三方源码。

标注口径：**A = 真实逐字复现（可判定为许可污染）**；**B = 惯用写法/公共片段巧合**；**C = 无法判断**。两名标注人各自填列，不一致样本交第三人复核并记录结论。

| 样本 | 来源项目 | 原文许可 | 论文 bleu | 论文 jaccard | CodeGuard 最高风险 | 逐字命中(token) | 覆盖率 | 归属正确 | 标注1 | 标注2 | 复核 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0205340e71ba | Ao-Lee_FacialVarification | Apache-2.0 | 0.76 | 0.57 | S1 | 43 | 0.50 | 是 | A | A | — |
| a2e4b2e0fa39 | Ao-Lee_FacialVarification | Apache-2.0 | 0.87 | 0.79 | S1 | 48 | 0.86 | 否 | A | A | — |
| e0d296846255 | Ao-Lee_FacialVarification | Apache-2.0 | 0.70 | 0.57 | S1 | 38 | 0.50 | 否 | B | A | A |
| 265538ed3798 | ascentai_rgan | Apache-2.0 | 0.88 | 0.77 | S1 | 45 | 0.33 | 是 | A | A | — |
| 5a3a5cc225bc | devsangwoo_tensor | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 否 | A | A | — |
| 063c525d98cd | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.78 | 0.62 | S1 | 48 | 0.33 | 是 | A | A | — |
| 94c4b0db9a13 | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.94 | 0.91 | S1 | 48 | 0.53 | 是 | A | A | — |
| b9b6837193dc | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.94 | 0.82 | S1 | 48 | 0.41 | 是 | A | A | — |
| dc6235b4da79 | gitlab.com_inverseai_Microso | MIT | 0.87 | 0.57 | S1 | 48 | 0.43 | 是 | A | A | — |
| b3bdb65a5b5e | gitlab.com_quicla_platform/c | Apache-2.0 | 0.65 | 0.39 | S1 | 22 | 0.67 | 是 | A | A | — |
| 1e7d53acf8e9 | googlesamples_assistant-sdk- | Apache-2.0 | 0.67 | 0.35 | S1 | 33 | 0.60 | 是 | A | A | — |
| ba67517b765e | hoppaq_masktextspotter.caffe | Apache-2.0 | 0.60 | 0.48 | S1 | 46 | 0.58 | 是 | A | A | — |
| d972ba3e3a98 | hoppaq_masktextspotter.caffe | Apache-2.0 | 0.98 | 0.94 | S1 | 48 | 0.43 | 是 | A | A | — |
| 523a3e34b273 | jwyang_faster-rcnn.pytorch | Apache-2.0 | 0.77 | 0.53 | S1 | 47 | 0.50 | 是 | A | A | — |
| 96303f3984c4 | matveevi_temp | Apache-2.0 | 0.89 | 0.78 | S1 | 48 | 0.50 | 是 | A | A | — |
| 13d07a9a7e71 | pjreddie_darknet | MIT | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 | A | A | — |
| 0a82a92bd4ea | princewen_tensorflow_practic | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 | A | A | — |
| 35c00596f963 | ruotianluo_pytorch-faster-rc | MIT | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 | A | A | — |
| 005165af96df | scikit-learn_scikit-learn | BSD-3-Clause | 0.71 | 0.45 | S1 | 33 | 0.33 | 是 | A | A | — |
| 0da014417270 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.67 | S1 | 48 | 0.44 | 是 | A | A | — |
| 259c8f1c13ee | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 否 | A | A | — |
| 3b91de32b1c9 | scikit-learn_scikit-learn | BSD-3-Clause | 0.64 | 0.57 | S1 | 47 | 0.44 | 是 | A | A | — |
| 58e2dfbefccb | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 是 | A | A | — |
| 5cb44df0f70f | scikit-learn_scikit-learn | BSD-3-Clause | 0.58 | 0.54 | S1 | 48 | 0.83 | 是 | A | A | — |
| 798ae8c02d0d | scikit-learn_scikit-learn | BSD-3-Clause | 0.67 | 0.51 | S1 | 47 | 0.30 | 是 | A | A | — |
| 7afc0b3ab029 | scikit-learn_scikit-learn | BSD-3-Clause | 0.70 | 0.32 | S2 | 42 | 0.24 | 是 | A | A | — |
| 933c9d021919 | scikit-learn_scikit-learn | BSD-3-Clause | 0.59 | 0.63 | S1 | 48 | 0.44 | 是 | A | A | — |
| 95da2ea12940 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.67 | S1 | 48 | 0.44 | 是 | A | A | — |
| f42eb9d83798 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 否 | A | A | — |
| f831a1326179 | scikit-learn_scikit-learn | BSD-3-Clause | 0.83 | 0.65 | S1 | 48 | 0.67 | 是 | A | A | — |
| 707625aaa76a | tensorflow_models | Apache-2.0 | 0.79 | 0.89 | S1 | 48 | 0.92 | 否 | A | A | — |
| 8c63b19f3703 | tensorflow_models | Apache-2.0 | 0.79 | 0.89 | S1 | 48 | 0.92 | 否 | A | A | — |
| a57913f7c63c | tensorflow_models | Apache-2.0 | 0.66 | 0.41 | S1 | 43 | 0.33 | 否 | A | B | A |
| fab6c443cf3d | tensorflow_models | Apache-2.0 | 0.88 | 0.68 | S1 | 48 | 1.00 | 否 | A | A | — |
| 88f3fb428f89 | tensorflow_tensorflow | Apache-2.0 | 0.74 | 0.54 | S1 | 48 | 0.33 | 是 | A | A | — |
| aa521eabb1fc | tensorflow_tensorflow | Apache-2.0 | 0.85 | 0.73 | S1 | 40 | 0.25 | 是 | A | A | — |
| adda1f5e564f | tensorflow_tensorflow | Apache-2.0 | 0.90 | 0.70 | S1 | 48 | 0.50 | 否 | A | A | — |
| b174956e6041 | tensorflow_tensorflow | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 否 | A | A | — |
| e68c171d9c7e | tensorflow_tensorflow | Apache-2.0 | 0.81 | 0.53 | S1 | 48 | 0.50 | 是 | A | A | — |
| ebfaacb8a2c9 | tensorflow_tensorflow | Apache-2.0 | 0.69 | 0.52 | S1 | 45 | 0.40 | 是 | A | A | — |
| f4a177c87710 | tensorflow_tfjs-examples | Apache-2.0 | 0.96 | 0.85 | S1 | 40 | 1.00 | 是 | A | A | — |
| cbe2f672e4f4 | GeoNode_geonode | GPL-3.0-or-later | 0.72 | 0.47 | S4 | 24 | 0.50 | 是 | B | A | A |
| b990893eda84 | calamares_calamares | GPL-3.0-or-later | 0.56 | 0.30 | S4 | 19 | 0.50 | 是 | A | A | — |
| 9d8debef7cbc | jsculsp_data-structures-and- | GPL-3.0-or-later | 0.70 | 0.54 | S4 | 44 | 1.00 | 是 | A | A | — |
| e9eef7741875 | jsculsp_data-structures-and- | GPL-3.0-or-later | 0.89 | 0.74 | S4 | 48 | 0.33 | 是 | A | A | — |
| eef13de1982b | thakrah_Learning.Python | GPL-3.0-or-later | 0.69 | 0.48 | S4 | 48 | 0.75 | 是 | A | A | — |
| 0b83cf315f51 | mozilla_gecko-dev | MPL-2.0 | 0.98 | 0.86 | S3 | 48 | 0.75 | 是 | A | A | — |

- 标注人1：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
- 标注人2：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
- 分歧样本与复核结论：＿＿＿＿＿＿＿＿＿＿＿＿＿＿
