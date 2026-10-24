# LiCoEval 47 条正例双人标注汇总

> 本文件由 `scripts/merge_annotations.py` 从两份独立 CSV 生成，未修改任何标签。
> 生成时间：2026-10-25 00:44。A = 实质逐字复现；B = 惯用写法/公共片段；C = 无法判断。
> 论文把 47 条都标为 striking-similar（copied）；本表的 A 是团队独立确认，B/C 是不确认/拿不准，不能把两者混写。

## 一、汇总

| 指标 | 结果 |
|---|---|
| 样本数 | 47 |
| 标注人1 分布 | A 45 / B 2 / C 0 |
| 标注人2 分布 | A 46 / B 1 / C 0 |
| 一致样本 | 44 / 47（93.6%） |
| Cohen's κ | -0.0292 |
| κ 解释 | 较差（<0.40）；低值主要由分布偏斜导致（见第四节），分歧已全部经第三人复核闭环（见第二节） |
| 分歧样本 | 3 |
| 已复核分歧 | 3 |
| 最终 A（独立确认复现） | 47 / 47 |

## 二、分歧样本（交第三人复核）

| 样本 | 项目 | 许可 | 标注人1 | 标注人2 | 标注人1 理由 | 标注人2 理由 | 复核结论 |
|---|---|---|---|---|---|---|---|
| e0d296846255ddca | Ao-Lee_FacialVarification | Apache-2.0 | B | A | 只共享了通用的TFRecord解析模板，没有复制默认值，图片shape和标签读取的核心实现 | — | A |
| cbe2f672e4f4ad03 | GeoNode_geonode | GPL-3.0-or-later | B | A | 只共享了版本号拼接的基础骨架，没有复制unstable状态下的git逻辑及特定的分支断言 | — | A |
| a57913f7c63c9ad5 | tensorflow_models | Apache-2.0 | A | B | — | 只共享了TensorFlow模型冻结的标准API和官方模板，错误处理不同，没有复制实现 | A |

## 三、逐条记录

| # | 样本 | 项目 | 许可 | 论文标签 | 标注人1 | 标注人2 | 一致 | 最终 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0205340e71baf62c | Ao-Lee_FacialVarification | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 2 | a2e4b2e0fa396143 | Ao-Lee_FacialVarification | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 3 | e0d296846255ddca | Ao-Lee_FacialVarification | Apache-2.0 | copied (paper) | B | A | 否 | A | 只共享了通用的TFRecord解析模板，没有复制默认值，图片shape和标签读取的核心实现 / 复核：逐字38 token、覆盖0.50；除通用TFRecord模板外还复制了读取与shape/标签处理实现，构成实质复现 |
| 4 | cbe2f672e4f4ad03 | GeoNode_geonode | GPL-3.0-or-later | copied (paper) | B | A | 否 | A | 只共享了版本号拼接的基础骨架，没有复制unstable状态下的git逻辑及特定的分支断言 / 复核：逐字24 token、覆盖0.50、CodeGuard S4 且归因正确；GPL原文的版本/分支逻辑被成段复现 |
| 5 | 265538ed37984464 | ascentai_rgan | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 6 | b990893eda84e69e | calamares_calamares | GPL-3.0-or-later | copied (paper) | A | A | 是 | A | — |
| 7 | 5a3a5cc225bc605d | devsangwoo_tensor | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 8 | 063c525d98cd91bb | gitlab.com_armbiant_pytorch-nlp | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 9 | 94c4b0db9a13d589 | gitlab.com_armbiant_pytorch-nlp | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 10 | b9b6837193dce194 | gitlab.com_armbiant_pytorch-nlp | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 11 | dc6235b4da79859c | gitlab.com_inverseai_Microsoft/CNTK | MIT | copied (paper) | A | A | 是 | A | — |
| 12 | b3bdb65a5b5efe06 | gitlab.com_quicla_platform/cts | Apache-2.0 | copied (paper) | A | A | 是 | A | 只共享处理硬件，非复制复现 |
| 13 | 1e7d53acf8e9b8e0 | googlesamples_assistant-sdk-python | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 14 | ba67517b765e2190 | hoppaq_masktextspotter.caffe2 | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 15 | d972ba3e3a98cd05 | hoppaq_masktextspotter.caffe2 | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 16 | 9d8debef7cbc172b | jsculsp_data-structures-and-algorithms-in-python | GPL-3.0-or-later | copied (paper) | A | A | 是 | A | — |
| 17 | e9eef7741875108f | jsculsp_data-structures-and-algorithms-in-python | GPL-3.0-or-later | copied (paper) | A | A | 是 | A | — |
| 18 | 523a3e34b2733f7e | jwyang_faster-rcnn.pytorch | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 19 | 96303f3984c418ce | matveevi_temp | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 20 | 0b83cf315f51ed82 | mozilla_gecko-dev | MPL-2.0 | copied (paper) | A | A | 是 | A | — |
| 21 | 13d07a9a7e71afae | pjreddie_darknet | MIT | copied (paper) | A | A | 是 | A | — |
| 22 | 0a82a92bd4ea80c3 | princewen_tensorflow_practice | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 23 | 35c00596f96319b6 | ruotianluo_pytorch-faster-rcnn | MIT | copied (paper) | A | A | 是 | A | — |
| 24 | 005165af96df953b | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 25 | 0da0144172703b6b | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 26 | 259c8f1c13ee3c4e | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 27 | 3b91de32b1c9f3c8 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 28 | 58e2dfbefccb5b25 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 29 | 5cb44df0f70fc987 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 30 | 798ae8c02d0df4d5 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 31 | 7afc0b3ab029ddc3 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 32 | 933c9d021919d92e | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 33 | 95da2ea129401c6a | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 34 | f42eb9d83798c452 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 35 | f831a1326179a9e8 | scikit-learn_scikit-learn | BSD-3-Clause | copied (paper) | A | A | 是 | A | — |
| 36 | 707625aaa76a12ca | tensorflow_models | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 37 | 8c63b19f3703fead | tensorflow_models | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 38 | a57913f7c63c9ad5 | tensorflow_models | Apache-2.0 | copied (paper) | A | B | 否 | A | 只共享了TensorFlow模型冻结的标准API和官方模板，错误处理不同，没有复制实现 / 复核：逐字43 token，超出模型冻结标准API调用范围，构成实质复现 |
| 39 | fab6c443cf3d2e97 | tensorflow_models | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 40 | 88f3fb428f896afd | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 41 | aa521eabb1fc2fea | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 42 | adda1f5e564fdcf6 | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 43 | b174956e6041db91 | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 44 | e68c171d9c7e33d7 | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 45 | ebfaacb8a2c969c4 | tensorflow_tensorflow | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 46 | f4a177c8771051a9 | tensorflow_tfjs-examples | Apache-2.0 | copied (paper) | A | A | 是 | A | — |
| 47 | eef13de1982b7e07 | thakrah_Learning.Python | GPL-3.0-or-later | copied (paper) | A | A | 是 | A | — |

## 四、解释与局限

- 这 47 条是 LiCoEval 按 striking-similar 筛出的正例，不是模型全部输出；本表衡量的是“团队是否独立确认这段相似构成实质复现”，不是法律结论。
- κ 只反映两名标注人对 A/B/C 口径的一致程度，不反映标注本身是否正确；κ 低于 0.60 时应先讨论口径、再重标，而不是直接交卷。
- κ 对分布偏斜敏感：如果一方几乎全判 A，即使一致率 95%+，κ 也可能接近 0。报告时同时写一致率和 κ，并说明这一点；不要把 κ=0 误读为双方完全不一致。
- 样本量 47，κ 的置信区间较宽；标注人未接受正式版权法培训，B/C 的边界仍应由第三人复核。
- 论文标签（copied）是样本入选依据；若团队最终 A 数少于 47，报告应写“独立确认 X/47”，不能写“47/47 确认为复现”。

## 五、可直接写入报告的句子（按实际数字替换）

> 两名成员对 LiCoEval 的 47 条 GPT-4o 真实输出独立标注：一致 44/47（93.6%），Cohen's κ=-0.0292；标注人1 判 A 45 / B 2 / C 0，标注人2 判 A 46 / B 1 / C 0；3 条分歧经第三人复核后，最终独立确认 A 47 条。

> κ 受分布偏斜影响（一方几乎全 A 时 κ 会接近 0），报告时与一致率并列给出，不要单独引用 κ。

## 六、复现

```bash
python scripts/make_annotation_packet.py
python scripts/merge_annotations.py --allow-blank   # 只检查模板，不生成完成结论
python scripts/merge_annotations.py                 # 两份 CSV 填满后生成正式汇总
```

标注口径与流程见 `submission/evidence/model-leak-20261021-标注说明.md`；对照包含第三方原文，只在本机 `.codeguard/annotation/` 打开，不入库、不上传。
