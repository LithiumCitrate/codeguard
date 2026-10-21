# 真实模型泄漏正例标注表（双人独立标注）

来源：LiCoEval（ICSE 2025，AGPL-3.0-or-later）公布的 GPT-4o 真实生成代码，以及论文判定与之 striking-similar 的开源原文。本表只列摘要与指标，不含第三方源码。

标注口径：**A = 真实逐字复现（可判定为许可污染）**；**B = 惯用写法/公共片段巧合**；**C = 无法判断**。两名标注人各自填列，不一致样本交第三人复核并记录结论。

| 样本 | 来源项目 | 原文许可 | 论文 bleu | 论文 jaccard | CodeGuard 最高风险 | 逐字命中(token) | 覆盖率 | 归属正确 | 标注1 | 标注2 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0205340e71ba | Ao-Lee_FacialVarification | Apache-2.0 | 0.76 | 0.57 | S1 | 43 | 0.50 | 是 |  |  |
| a2e4b2e0fa39 | Ao-Lee_FacialVarification | Apache-2.0 | 0.87 | 0.79 | S1 | 48 | 0.86 | 否 |  |  |
| e0d296846255 | Ao-Lee_FacialVarification | Apache-2.0 | 0.70 | 0.57 | S1 | 38 | 0.50 | 否 |  |  |
| 265538ed3798 | ascentai_rgan | Apache-2.0 | 0.88 | 0.77 | S1 | 45 | 0.33 | 是 |  |  |
| 5a3a5cc225bc | devsangwoo_tensor | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 否 |  |  |
| 063c525d98cd | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.78 | 0.62 | S1 | 48 | 0.33 | 是 |  |  |
| 94c4b0db9a13 | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.94 | 0.91 | S1 | 48 | 0.53 | 是 |  |  |
| b9b6837193dc | gitlab.com_armbiant_pytorch- | Apache-2.0 | 0.94 | 0.82 | S1 | 48 | 0.41 | 是 |  |  |
| dc6235b4da79 | gitlab.com_inverseai_Microso | MIT | 0.87 | 0.57 | S1 | 48 | 0.43 | 是 |  |  |
| b3bdb65a5b5e | gitlab.com_quicla_platform/c | Apache-2.0 | 0.65 | 0.39 | S1 | 22 | 0.67 | 是 |  |  |
| 1e7d53acf8e9 | googlesamples_assistant-sdk- | Apache-2.0 | 0.67 | 0.35 | S1 | 33 | 0.60 | 是 |  |  |
| ba67517b765e | hoppaq_masktextspotter.caffe | Apache-2.0 | 0.60 | 0.48 | S1 | 46 | 0.58 | 是 |  |  |
| d972ba3e3a98 | hoppaq_masktextspotter.caffe | Apache-2.0 | 0.98 | 0.94 | S1 | 48 | 0.43 | 是 |  |  |
| 523a3e34b273 | jwyang_faster-rcnn.pytorch | Apache-2.0 | 0.77 | 0.53 | S1 | 47 | 0.50 | 是 |  |  |
| 96303f3984c4 | matveevi_temp | Apache-2.0 | 0.89 | 0.78 | S1 | 48 | 0.50 | 是 |  |  |
| 13d07a9a7e71 | pjreddie_darknet | MIT | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 |  |  |
| 0a82a92bd4ea | princewen_tensorflow_practic | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 |  |  |
| 35c00596f963 | ruotianluo_pytorch-faster-rc | MIT | 1.00 | 1.00 | S1 | 48 | 0.50 | 是 |  |  |
| 005165af96df | scikit-learn_scikit-learn | BSD-3-Clause | 0.71 | 0.45 | S1 | 33 | 0.33 | 是 |  |  |
| 0da014417270 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.67 | S1 | 48 | 0.44 | 是 |  |  |
| 259c8f1c13ee | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 否 |  |  |
| 3b91de32b1c9 | scikit-learn_scikit-learn | BSD-3-Clause | 0.64 | 0.57 | S1 | 47 | 0.44 | 是 |  |  |
| 58e2dfbefccb | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 是 |  |  |
| 5cb44df0f70f | scikit-learn_scikit-learn | BSD-3-Clause | 0.58 | 0.54 | S1 | 48 | 0.83 | 是 |  |  |
| 798ae8c02d0d | scikit-learn_scikit-learn | BSD-3-Clause | 0.67 | 0.51 | S1 | 47 | 0.30 | 是 |  |  |
| 7afc0b3ab029 | scikit-learn_scikit-learn | BSD-3-Clause | 0.70 | 0.32 | S2 | 42 | 0.24 | 是 |  |  |
| 933c9d021919 | scikit-learn_scikit-learn | BSD-3-Clause | 0.59 | 0.63 | S1 | 48 | 0.44 | 是 |  |  |
| 95da2ea12940 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.67 | S1 | 48 | 0.44 | 是 |  |  |
| f42eb9d83798 | scikit-learn_scikit-learn | BSD-3-Clause | 0.66 | 0.66 | S1 | 48 | 0.83 | 否 |  |  |
| f831a1326179 | scikit-learn_scikit-learn | BSD-3-Clause | 0.83 | 0.65 | S1 | 48 | 0.67 | 是 |  |  |
| 707625aaa76a | tensorflow_models | Apache-2.0 | 0.79 | 0.89 | S1 | 48 | 0.92 | 否 |  |  |
| 8c63b19f3703 | tensorflow_models | Apache-2.0 | 0.79 | 0.89 | S1 | 48 | 0.92 | 否 |  |  |
| a57913f7c63c | tensorflow_models | Apache-2.0 | 0.66 | 0.41 | S1 | 43 | 0.33 | 否 |  |  |
| fab6c443cf3d | tensorflow_models | Apache-2.0 | 0.88 | 0.68 | S1 | 48 | 1.00 | 否 |  |  |
| 88f3fb428f89 | tensorflow_tensorflow | Apache-2.0 | 0.74 | 0.54 | S1 | 48 | 0.33 | 是 |  |  |
| aa521eabb1fc | tensorflow_tensorflow | Apache-2.0 | 0.85 | 0.73 | S1 | 40 | 0.25 | 是 |  |  |
| adda1f5e564f | tensorflow_tensorflow | Apache-2.0 | 0.90 | 0.70 | S1 | 48 | 0.50 | 否 |  |  |
| b174956e6041 | tensorflow_tensorflow | Apache-2.0 | 1.00 | 1.00 | S1 | 48 | 0.50 | 否 |  |  |
| e68c171d9c7e | tensorflow_tensorflow | Apache-2.0 | 0.81 | 0.53 | S1 | 48 | 0.50 | 是 |  |  |
| ebfaacb8a2c9 | tensorflow_tensorflow | Apache-2.0 | 0.69 | 0.52 | S1 | 45 | 0.40 | 是 |  |  |
| f4a177c87710 | tensorflow_tfjs-examples | Apache-2.0 | 0.96 | 0.85 | S1 | 40 | 1.00 | 是 |  |  |
| cbe2f672e4f4 | GeoNode_geonode | GPL-3.0-or-later | 0.72 | 0.47 | S4 | 24 | 0.50 | 是 |  |  |
| b990893eda84 | calamares_calamares | GPL-3.0-or-later | 0.56 | 0.30 | S4 | 19 | 0.50 | 是 |  |  |
| 9d8debef7cbc | jsculsp_data-structures-and- | GPL-3.0-or-later | 0.70 | 0.54 | S4 | 44 | 1.00 | 是 |  |  |
| e9eef7741875 | jsculsp_data-structures-and- | GPL-3.0-or-later | 0.89 | 0.74 | S4 | 48 | 0.33 | 是 |  |  |
| eef13de1982b | thakrah_Learning.Python | GPL-3.0-or-later | 0.69 | 0.48 | S4 | 48 | 0.75 | 是 |  |  |
| 0b83cf315f51 | mozilla_gecko-dev | MPL-2.0 | 0.98 | 0.86 | S3 | 48 | 0.75 | 是 |  |  |

- 标注人1：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
- 标注人2：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
- 分歧样本与复核结论：＿＿＿＿＿＿＿＿＿＿＿＿＿＿
