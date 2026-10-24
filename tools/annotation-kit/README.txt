CodeGuard 标注与汇总工具包
=====================================

给队友的最短路径：

1. 双击 start.bat
   如果没反应，把 annotate.html 拖进 Edge 或 Chrome。

2. 选择“我是标注人1”或“我是标注人2”。

3. 对 47 条样本逐条点 A / B / C。
   - A：确实复制了一段有表达性的实现。
   - B：只是 imports、argparse、短签名、docstring、通用写法。
   - C：看不准。拿不准就 C。

4. 做完后点“导出我的 CSV”，把 CSV 发给队长。

不要转发 annotate.html，不要截图第三方原文。CSV 可以发给队长。

详细教程：TUTORIAL.md
试用材料：trial/
数据许可：LICENSE-LiCoEval.txt（AGPL-3.0-or-later，只供队内本地标注使用）

底线：
- A/B/C 必须本人判断，不能全选 A，不能看队友答案。
- 试用反馈必须来自非项目成员本人填写的原始表。
- 工具只做证据准备、导出、统计和汇总，不替人判断。
