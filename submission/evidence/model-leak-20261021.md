# 真实模型泄漏正例评测（LiCoEval / GPT-4o 生成代码）

- 样本：47（clean 0 / copied 47）
- 生成时间：2026-10-21T10:15:42Z
- 判定阈值：fail_on=S3,S4，min_span_prob=0.55
- 数据集：LiCoEval real regurgitation cases (gpt-4o) （AGPL-3.0-or-later；SHA-256 `f3561838ff8c9d8224d026edbffbe6de47cbab90327f44585a16ef2e120c96e0`）
- 来源：https://github.com/osslab-pku/LiCoEval

## 汇总

| 指标 | 数值 |
|---|---|
| 复制样本归因到预期来源 | 36 / 47（76.60%） |
| 复制样本达到阻断阈值 | 6 / 47（12.77%） |
| 复制样本 top-1 来源正确 | 21 / 47（44.68%） |
| 片段总数 / 命中片段 | 456 / 348 |
| 单样本耗时 p50 / p95 / max | 97.4 / 363.8 / 1149.6 ms |

## 风险分布（命中条数）

| S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| 43 | 63 | 1 | 2 | 5 |

## 未通过样本

| 样本 | 标签 | 最高风险 | 说明 |
|---|---|---|---|
| leak-005165af96df953b | copied | S1 | scikit-learn_scikit-learn@gpt-4o-005165af:scikit-learn_scikit-learn/005165af96df953b.py |
| leak-0205340e71baf62c | copied | S1 | Ao-Lee_FacialVarification@gpt-4o-bab406a8:Ao-Lee_FacialVarification/bab406a8cf2c7c26.py, Ao-Lee_FacialVarification@gpt-4o-0205340e:Ao-Lee_FacialVarification/0205340e71baf62c.py |
| leak-063c525d98cd91bb | copied | S1 | gitlab.com_armbiant_pytorch-nlp@gpt-4o-94c4b0db:gitlab.com_armbiant_pytorch-nlp/94c4b0db9a13d589.py, gitlab.com_armbiant_pytorch-nlp@gpt-4o-9936e720:gitlab.com_armbiant_pytorch-nlp/9936e72030496a35.py |
| leak-0a82a92bd4ea80c3 | copied | S1 | shenweichen_DeepCTR@gpt-4o-b3554993:shenweichen_DeepCTR/b3554993063ad297.py, princewen_tensorflow_practice@gpt-4o-0a82a92b:princewen_tensorflow_practice/0a82a92bd4ea80c3.py |
| leak-0da0144172703b6b | copied | S1 | scikit-learn_scikit-learn@gpt-4o-95da2ea1:scikit-learn_scikit-learn/95da2ea129401c6a.py, scikit-learn_scikit-learn@gpt-4o-933c9d02:scikit-learn_scikit-learn/933c9d021919d92e.py |
| leak-13d07a9a7e71afae | copied | S1 | hoppaq_masktextspotter.caffe2@gpt-4o-d972ba3e:hoppaq_masktextspotter.caffe2/d972ba3e3a98cd05.py, ruotianluo_pytorch-faster-rcnn@gpt-4o-35c00596:ruotianluo_pytorch-faster-rcnn/35c00596f96319b6.py |
| leak-1e7d53acf8e9b8e0 | copied | S1 | googlesamples_assistant-sdk-python@gpt-4o-1e7d53ac:googlesamples_assistant-sdk-python/1e7d53acf8e9b8e0.py |
| leak-259c8f1c13ee3c4e | copied | S1 | scikit-learn_scikit-learn@gpt-4o-58e2dfbe:scikit-learn_scikit-learn/58e2dfbefccb5b25.py, scikit-learn_scikit-learn@gpt-4o-5cb44df0:scikit-learn_scikit-learn/5cb44df0f70fc987.py |
| leak-265538ed37984464 | copied | S1 | ascentai_rgan@gpt-4o-265538ed:ascentai_rgan/265538ed37984464.py, tensorflow_tensorflow@gpt-4o-88f3fb42:tensorflow_tensorflow/88f3fb428f896afd.py |
| leak-35c00596f96319b6 | copied | S1 | hoppaq_masktextspotter.caffe2@gpt-4o-d972ba3e:hoppaq_masktextspotter.caffe2/d972ba3e3a98cd05.py, ruotianluo_pytorch-faster-rcnn@gpt-4o-35c00596:ruotianluo_pytorch-faster-rcnn/35c00596f96319b6.py |
| leak-3b91de32b1c9f3c8 | copied | S1 | scikit-learn_scikit-learn@gpt-4o-798ae8c0:scikit-learn_scikit-learn/798ae8c02d0df4d5.py, scikit-learn_scikit-learn@gpt-4o-3b91de32:scikit-learn_scikit-learn/3b91de32b1c9f3c8.py |
| leak-523a3e34b2733f7e | copied | S1 | jwyang_faster-rcnn.pytorch@gpt-4o-523a3e34:jwyang_faster-rcnn.pytorch/523a3e34b2733f7e.py |
| leak-58e2dfbefccb5b25 | copied | S1 | scikit-learn_scikit-learn@gpt-4o-58e2dfbe:scikit-learn_scikit-learn/58e2dfbefccb5b25.py, scikit-learn_scikit-learn@gpt-4o-5cb44df0:scikit-learn_scikit-learn/5cb44df0f70fc987.py |
| leak-5a3a5cc225bc605d | copied | S1 | shenweichen_DeepCTR@gpt-4o-b3554993:shenweichen_DeepCTR/b3554993063ad297.py, princewen_tensorflow_practice@gpt-4o-0a82a92b:princewen_tensorflow_practice/0a82a92bd4ea80c3.py |
| leak-5cb44df0f70fc987 | copied | S1 | scikit-learn_scikit-learn@gpt-4o-58e2dfbe:scikit-learn_scikit-learn/58e2dfbefccb5b25.py, scikit-learn_scikit-learn@gpt-4o-5cb44df0:scikit-learn_scikit-learn/5cb44df0f70fc987.py |
| leak-707625aaa76a12ca | copied | S1 | balancap_SSD-Tensorflow@gpt-4o-3a17a7f5:balancap_SSD-Tensorflow/3a17a7f50771322b.py, tensorflow_tensor2tensor@gpt-4o-660d3c94:tensorflow_tensor2tensor/660d3c943c9e0206.py |
| leak-798ae8c02d0df4d5 | copied | S1 | scikit-learn_scikit-learn@gpt-4o-95da2ea1:scikit-learn_scikit-learn/95da2ea129401c6a.py, scikit-learn_scikit-learn@gpt-4o-798ae8c0:scikit-learn_scikit-learn/798ae8c02d0df4d5.py |
| leak-7afc0b3ab029ddc3 | copied | S2 | scikit-learn_scikit-learn@gpt-4o-29707ac9:scikit-learn_scikit-learn/29707ac94cf70174.py, scikit-learn_scikit-learn@gpt-4o-7afc0b3a:scikit-learn_scikit-learn/7afc0b3ab029ddc3.py |
| leak-88f3fb428f896afd | copied | S1 | tensorflow_tensorflow@gpt-4o-88f3fb42:tensorflow_tensorflow/88f3fb428f896afd.py, tensorflow_tensorflow@gpt-4o-aa521eab:tensorflow_tensorflow/aa521eabb1fc2fea.py |
| leak-8c63b19f3703fead | copied | S1 | balancap_SSD-Tensorflow@gpt-4o-3a17a7f5:balancap_SSD-Tensorflow/3a17a7f50771322b.py, tensorflow_tensor2tensor@gpt-4o-660d3c94:tensorflow_tensor2tensor/660d3c943c9e0206.py |
| leak-933c9d021919d92e | copied | S1 | scikit-learn_scikit-learn@gpt-4o-95da2ea1:scikit-learn_scikit-learn/95da2ea129401c6a.py, scikit-learn_scikit-learn@gpt-4o-933c9d02:scikit-learn_scikit-learn/933c9d021919d92e.py |
| leak-94c4b0db9a13d589 | copied | S1 | gitlab.com_armbiant_pytorch-nlp@gpt-4o-b9b68371:gitlab.com_armbiant_pytorch-nlp/b9b6837193dce194.py, gitlab.com_armbiant_pytorch-nlp@gpt-4o-94c4b0db:gitlab.com_armbiant_pytorch-nlp/94c4b0db9a13d589.py |
| leak-95da2ea129401c6a | copied | S1 | scikit-learn_scikit-learn@gpt-4o-95da2ea1:scikit-learn_scikit-learn/95da2ea129401c6a.py, scikit-learn_scikit-learn@gpt-4o-933c9d02:scikit-learn_scikit-learn/933c9d021919d92e.py |
| leak-96303f3984c418ce | copied | S1 | matveevi_temp@gpt-4o-96303f39:matveevi_temp/96303f3984c418ce.py, tensorflow_models@gpt-4o-018e2f26:tensorflow_models/018e2f26ea57ab40.py |
| leak-a2e4b2e0fa396143 | copied | S1 | vlnguyen92_tfhybrid@gpt-4o-8b01ac7f:vlnguyen92_tfhybrid/8b01ac7fd498bfbc.py |
| leak-a57913f7c63c9ad5 | copied | S1 | tensorflow_tensorflow@gpt-4o-80699509:tensorflow_tensorflow/8069950925d41d64.py, tensorflow_tensorflow@gpt-4o-e9f1def4:tensorflow_tensorflow/e9f1def48c462dcd.py |
| leak-aa521eabb1fc2fea | copied | S1 | ascentai_rgan@gpt-4o-265538ed:ascentai_rgan/265538ed37984464.py, tensorflow_tensorflow@gpt-4o-aa521eab:tensorflow_tensorflow/aa521eabb1fc2fea.py |
| leak-adda1f5e564fdcf6 | copied | S1 | shenweichen_DeepCTR@gpt-4o-b3554993:shenweichen_DeepCTR/b3554993063ad297.py, princewen_tensorflow_practice@gpt-4o-0a82a92b:princewen_tensorflow_practice/0a82a92bd4ea80c3.py |
| leak-b174956e6041db91 | copied | S1 | shenweichen_DeepCTR@gpt-4o-b3554993:shenweichen_DeepCTR/b3554993063ad297.py, princewen_tensorflow_practice@gpt-4o-0a82a92b:princewen_tensorflow_practice/0a82a92bd4ea80c3.py |
| leak-b3bdb65a5b5efe06 | copied | S1 | gitlab.com_quicla_platform_cts@gpt-4o-b3bdb65a:gitlab.com_quicla_platform_cts/b3bdb65a5b5efe06.py |

## 说明

- 本评测只覆盖清单中的样本与当前语料；未出现的语言、项目或生成方式不受此结果保证。
- 复制样本按预期来源计算归因；未指定 source_package 的样本只统计阻断。
- 本清单 47 条正例里只有 6 条原文是 copyleft（5 条 GPL-3.0-or-later、1 条 MPL-2.0），其余 41 条原文为 Apache-2.0/BSD-3-Clause/MIT，按 MIT 目标分发不构成许可证冲突；因此“达到阻断阈值 6/47”只对这 6 条子集有意义，子集阻断为 6/6。
- 通用渲染器的“未通过样本”按 copied 且未阻断定义，对宽松许可正例而言未阻断是预期结果，不是失败；请按“出现任意命中 47/47”与“归因到预期项目 39/47”读这张表。

## 真实泄漏正例检出

- 正例：47 条（论文判定的 striking-similarity 案例，模型输出为 GPT-4o 真实生成）
- 同索引参考语料：4187 个带许可标注的真实开源代码窗口
- 许可家族分布：{"permissive": 41, "weak": 1, "strong": 5}

| 指标 | 数值 | 95% 单侧下限 |
|---|---|---|
| 归因到预期项目/路径 | 36 / 47 | 64.2% |
| 归因到预期项目（同项目不同窗口/副本） | 39 / 47 | 71.4% |
| 命中同摘要原文（含跨项目副本） | 36 / 47 | 64.2% |
| 归因到预期项目或同摘要等效来源 | 36 / 47 | 64.2% |
| top-1 即预期来源 | 21 / 47 | 32.2% |
| copyleft 子集达到阻断阈值 | 6 / 6 | 100.0% |
| 出现任意命中 | 47 / 47 | 100.0% |
| 最长逐字命中 中位/最大/≥20 token | 48.0 / 48 / 46 | - |
| 真源排名 top1 / top3 / 未上榜 | 21 / 33 / 11 | - |

（逐字命中以 48 token 的滑窗为上限，表中 48 读作“至少 48”。归属分级：{"expected_doc": 36, "same_project": 3, "other_project": 8}。）

- “别的项目”不是误报：这些命中的是**同一段上游代码的其它复制仓库**（tensorflow_models → balancap_SSD-Tensorflow、tensorflow_tensorflow → shenweichen_DeepCTR 等）。逐条命中项目已在下表列出，是否认定更强来源需人工标注；文件级归因 36/47 与项目级归因 39/47 都按最保守口径统计（只认预期项目/路径）。

## 同索引对照：真实开源文件（排除自身项目）

- 样本 200；阻断级文件 7；单侧 95% 上限 6.47%；出现任意命中 122
- 阻断命中分类：{"cross_project": 7}（same_text=同一份代码被别的项目复制走，same_project=同项目不同窗口，cross_project=跨项目相似）
- 风险分布：{"S0": 247, "S1": 41, "S2": 12, "S3": 2, "S4": 5}；p95 耗时 714.2 ms
- 查询与候选都是真实开源代码，且参考语料里同一个上游文件常被多个项目各自复制，所以这里的阻断不是误报率：摘要一致/同项目命中属于真实的跨仓库重复（vendoring）。误阻断率见 HumanEval 外部评测与 false_block_control.py 的产品口径。

| 查询项目 | 命中来源 | 命中许可 | 风险 | 类型 | 逐字 | 覆盖率 | 置信度 |
|---|---|---|---|---|---|---|---|
| Lothiraldan_cvs | 50b434be7ffbd98b.py | GPL-2.0-or-later | S3 | cross_project | 32 | 0.05 | 0.61 |
| twbs_bootstrap | a085f78c439022f1.py | GPL-2.0-only | S4 | cross_project | 48 | 0.47 | 1.00 |
| indygreg_hg | 3aff3293a325701e.py | GPL-2.0-or-later | S4 | cross_project | 9 | 0.13 | 0.77 |
| weechat_scripts | c095f488474b6275.py | GPL-3.0-or-later | S4 | cross_project | 6 | 0.42 | 0.98 |
| indygreg_hg | dd4d29c6790e78f8.py | GPL-2.0-or-later | S4 | cross_project | 16 | 0.25 | 0.86 |
| jordigh_mercurial-crew | bd15a822bdd0b1d8.py | GPL-2.0-or-later | S4 | cross_project | 46 | 0.30 | 0.96 |
| mozilla_mozbase-deprec | 6b495f2dd5a3cb98.py | MPL-2.0 | S3 | cross_project | 27 | 0.08 | 0.60 |

## 按许可证的检出

| 许可证 | 家族 | 条数 | 归因 | 阻断 | 逐字命中(最大) |
|---|---|---|---|---|---|
| Apache-2.0 | permissive | 26 | 17 | 0 | 48 |
| BSD-3-Clause | permissive | 12 | 10 | 0 | 48 |
| GPL-3.0-or-later | strong | 5 | 5 | 5 | 48 |
| MIT | permissive | 3 | 3 | 0 | 48 |
| MPL-2.0 | weak | 1 | 1 | 1 | 48 |

## 正例逐条（只记录摘要与指标，不写入第三方源码）

| 样本 | 来源项目 | 许可 | 风险 | 归属 | 实际命中项目 | 真源排名 | 逐字 | 覆盖率 | 置信度 |
|---|---|---|---|---|---|---|---|---|---|
| 063c525d98cd | gitlab.com_armbiant_pyto | Apache-2.0 | S1 | 预期文档 | gitlab.com_armbiant_py | 5 | 48 | 0.33 | 0.99 |
| 0a82a92bd4ea | princewen_tensorflow_pra | Apache-2.0 | S1 | 预期文档 | princewen_tensorflow_p, shenweichen_DeepCTR | 2 | 48 | 0.50 | 1.00 |
| 0b83cf315f51 | mozilla_gecko-dev | MPL-2.0 | S3 | 预期文档 | mozilla_gecko-dev | 1 | 48 | 0.75 | 1.00 |
| 0da014417270 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 4 | 48 | 0.44 | 1.00 |
| 13d07a9a7e71 | pjreddie_darknet | MIT | S1 | 预期文档 | apache_incubator-mxnet, hoppaq_masktextspotter, pjreddie_darknet | 4 | 48 | 0.50 | 1.00 |
| 259c8f1c13ee | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 同项目其它窗口 | scikit-learn_scikit-le | 0 | 48 | 0.83 | 1.00 |
| 35c00596f963 | ruotianluo_pytorch-faste | MIT | S1 | 预期文档 | apache_incubator-mxnet, hoppaq_masktextspotter, pjreddie_darknet | 2 | 48 | 0.50 | 1.00 |
| 58e2dfbefccb | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 1 | 48 | 0.83 | 1.00 |
| 5a3a5cc225bc | devsangwoo_tensor | Apache-2.0 | S1 | 别的项目 | princewen_tensorflow_p, shenweichen_DeepCTR | 0 | 48 | 0.50 | 1.00 |
| 5cb44df0f70f | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 2 | 48 | 0.83 | 0.99 |
| 707625aaa76a | tensorflow_models | Apache-2.0 | S1 | 别的项目 | balancap_SSD-Tensorflo, tensorflow_tensor2tens | 0 | 48 | 0.92 | 1.00 |
| 88f3fb428f89 | tensorflow_tensorflow | Apache-2.0 | S1 | 预期文档 | ascentai_rgan, tensorflow_models, tensorflow_tensorflow | 1 | 48 | 0.33 | 1.00 |
| 8c63b19f3703 | tensorflow_models | Apache-2.0 | S1 | 别的项目 | balancap_SSD-Tensorflo, tensorflow_tensor2tens | 0 | 48 | 0.92 | 1.00 |
| 933c9d021919 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 2 | 48 | 0.44 | 1.00 |
| 94c4b0db9a13 | gitlab.com_armbiant_pyto | Apache-2.0 | S1 | 预期文档 | gitlab.com_armbiant_py | 2 | 48 | 0.53 | 0.99 |
| 95da2ea12940 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 1 | 48 | 0.44 | 1.00 |
| 96303f3984c4 | matveevi_temp | Apache-2.0 | S1 | 预期文档 | matveevi_temp, tensorflow_models | 1 | 48 | 0.50 | 1.00 |
| a2e4b2e0fa39 | Ao-Lee_FacialVarificatio | Apache-2.0 | S1 | 别的项目 | vlnguyen92_tfhybrid | 0 | 48 | 0.86 | 0.99 |
| adda1f5e564f | tensorflow_tensorflow | Apache-2.0 | S1 | 别的项目 | princewen_tensorflow_p, shenweichen_DeepCTR | 0 | 48 | 0.50 | 1.00 |
| b174956e6041 | tensorflow_tensorflow | Apache-2.0 | S1 | 别的项目 | princewen_tensorflow_p, shenweichen_DeepCTR | 0 | 48 | 0.50 | 1.00 |
| b9b6837193dc | gitlab.com_armbiant_pyto | Apache-2.0 | S1 | 预期文档 | gitlab.com_armbiant_py | 1 | 48 | 0.41 | 0.99 |
| d972ba3e3a98 | hoppaq_masktextspotter.c | Apache-2.0 | S1 | 预期文档 | apache_incubator-mxnet, hoppaq_masktextspotter, pjreddie_darknet | 1 | 48 | 0.43 | 0.99 |
| dc6235b4da79 | gitlab.com_inverseai_Mic | MIT | S1 | 预期文档 | gitlab.com_inverseai_M, hoppaq_masktextspotter, pjreddie_darknet | 3 | 48 | 0.43 | 0.99 |
| e68c171d9c7e | tensorflow_tensorflow | Apache-2.0 | S1 | 预期文档 | tensorflow_tensorflow | 2 | 48 | 0.50 | 0.99 |
| e9eef7741875 | jsculsp_data-structures- | GPL-3.0-or-later | S4 | 预期文档 | jsculsp_data-structure | 1 | 48 | 0.33 | 1.00 |
| eef13de1982b | thakrah_Learning.Python | GPL-3.0-or-later | S4 | 预期文档 | thakrah_Learning.Pytho | 1 | 48 | 0.75 | 1.00 |
| f42eb9d83798 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 同项目其它窗口 | scikit-learn_scikit-le | 0 | 48 | 0.83 | 1.00 |
| f831a1326179 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 1 | 48 | 0.67 | 1.00 |
| fab6c443cf3d | tensorflow_models | Apache-2.0 | S1 | 别的项目 | vlnguyen92_tfhybrid | 0 | 48 | 1.00 | 1.00 |
| 3b91de32b1c9 | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 2 | 47 | 0.44 | 1.00 |
| 523a3e34b273 | jwyang_faster-rcnn.pytor | Apache-2.0 | S1 | 预期文档 | jwyang_faster-rcnn.pyt | 1 | 47 | 0.50 | 0.99 |
| 798ae8c02d0d | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 2 | 47 | 0.30 | 0.96 |
| ba67517b765e | hoppaq_masktextspotter.c | Apache-2.0 | S1 | 预期文档 | hoppaq_masktextspotter | 1 | 46 | 0.58 | 1.00 |
| 265538ed3798 | ascentai_rgan | Apache-2.0 | S1 | 预期文档 | ascentai_rgan, tensorflow_tensorflow | 1 | 45 | 0.33 | 0.98 |
| ebfaacb8a2c9 | tensorflow_tensorflow | Apache-2.0 | S1 | 预期文档 | horovod_horovod, hzy46_Deep-Learning-21, tensorflow_tensorflow | 1 | 45 | 0.40 | 0.98 |
| 9d8debef7cbc | jsculsp_data-structures- | GPL-3.0-or-later | S4 | 预期文档 | jsculsp_data-structure | 1 | 44 | 1.00 | 0.99 |
| 0205340e71ba | Ao-Lee_FacialVarificatio | Apache-2.0 | S1 | 预期文档 | Ao-Lee_FacialVarificat, tensorflow_models | 2 | 43 | 0.50 | 0.99 |
| a57913f7c63c | tensorflow_models | Apache-2.0 | S1 | 同项目其它窗口 | ogvalt_min-tfs-client, tensorflow_models, tensorflow_tensorflow | 0 | 43 | 0.33 | 0.98 |
| 7afc0b3ab029 | scikit-learn_scikit-lear | BSD-3-Clause | S2 | 预期文档 | mjg_PyX-svn, scikit-learn_scikit-le | 2 | 42 | 0.24 | 0.88 |
| aa521eabb1fc | tensorflow_tensorflow | Apache-2.0 | S1 | 预期文档 | ascentai_rgan, tensorflow_tensorflow | 2 | 40 | 0.25 | 0.89 |
| f4a177c87710 | tensorflow_tfjs-examples | Apache-2.0 | S1 | 预期文档 | tensorflow_tfjs-exampl | 1 | 40 | 1.00 | 1.00 |
| e0d296846255 | Ao-Lee_FacialVarificatio | Apache-2.0 | S1 | 别的项目 | vlnguyen92_tfhybrid | 0 | 38 | 0.50 | 0.99 |
| 005165af96df | scikit-learn_scikit-lear | BSD-3-Clause | S1 | 预期文档 | scikit-learn_scikit-le | 1 | 33 | 0.33 | 0.85 |
| 1e7d53acf8e9 | googlesamples_assistant- | Apache-2.0 | S1 | 预期文档 | googlesamples_assistan | 1 | 33 | 0.60 | 0.96 |
| cbe2f672e4f4 | GeoNode_geonode | GPL-3.0-or-later | S4 | 预期文档 | GeoNode_geonode, chromium.googlesource. | 1 | 24 | 0.50 | 0.88 |
| b3bdb65a5b5e | gitlab.com_quicla_platfo | Apache-2.0 | S1 | 预期文档 | gitlab.com_quicla_plat | 1 | 22 | 0.67 | 0.95 |
| b990893eda84 | calamares_calamares | GPL-3.0-or-later | S4 | 预期文档 | calamares_calamares | 1 | 19 | 0.50 | 0.88 |

## 协议与限制

- 正例由论文按自身相似度阈值筛出（gpt-4o 的 47 条 striking-similarity），不是模型全部输出；
- 被评模型与提示词由第三方论文固定，我们无法审计该模型的训练数据；
- 语料成员条件是构造性的：真实原文必然在索引内，所以这里测的是检出与归因能力，不是覆盖率上限；
- 宽松许可原文按 MIT 目标分发不构成许可证冲突，因此只计入溯源而不计入阻断。
