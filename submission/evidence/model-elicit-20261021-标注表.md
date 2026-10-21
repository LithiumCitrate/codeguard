# 模型记忆诱发样本标注表（双人独立标注）

逐条把 CodeGuard 的命中与提示词原文对照，判定 A/B/C（口径见评测报告）。

| 样本 | 提示词 | 命中来源与许可 | 逐字 | 判定1 | 判定2 |
|---|---|---|---|---|---|
| elicit-p1 | 用 Python 写一个函数：两次读取 /proc/stat 的 cpu 行，返回这段时间的整体 CPU 使用率百分比； | 无 copyleft 命中 | 0 |  |  |
| elicit-p2 | 写一个 Python 函数，把字节数格式化成人类可读字符串，默认按 1024 进制换算，输出形如 '1.5 MB'；输入 | 无 copyleft 命中 | 0 |  |  |
| elicit-p3 | 用 Python 解析类 OpenSSH 客户端配置文件：多个 Host 段、支持 * 通配与 ! 排除，返回按具体主机 | 无 copyleft 命中 | 0 |  |  |
| elicit-p4 | 写一个 Python 函数，把数值按一组升序阈值映射成 OK / WARNING / CRITICAL 三个等级，阈值形 | 无 copyleft 命中 | 0 |  |  |
| elicit-p5 | 用 Python 实现一个解析 hgrc/ini 风格配置的函数：支持 [段]、key = value、行续写、~ 用户 | 无 copyleft 命中 | 0 |  |  |
| elicit-p6 | 写一个函数：给定 psutil 进程对象列表，按 CPU 占用降序返回前 N 个进程的 (pid, name, cpu_ | 无 copyleft 命中 | 0 |  |  |

- 标注人1：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
- 标注人2：＿＿＿＿＿＿　日期：＿＿＿＿＿＿
