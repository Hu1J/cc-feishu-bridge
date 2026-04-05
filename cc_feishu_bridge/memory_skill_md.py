"""Inline skill content for cc-memory-search.

Bundled inside the package so it works via pip or PyInstaller binary.
"""
from __future__ import annotations

SKILL_NAME = "cc-memory-search"
SKILL_VERSION = "1.0.0"

SKILL_MD = """\
---
name: cc-memory-search
version: 1.0.0
description: |
  当你遇到报错、构建失败、测试失败或其他技术问题时，
  使用此工具搜索本地记忆库，查找之前是否遇到过同样的问题及解决方案。
  调用方式: cc-feishu-bridge memory search <问题关键词>
---

## 何时使用

当你遇到以下情况时，请优先使用本 skill 查询记忆库：

- **报错信息**：编译报错、运行时异常、测试失败
- **工具不工作**：某个工具或命令执行失败
- **重复问题**：感觉之前遇到过同样的问题
- **用户提及**：用户说"之前也是这样"、"上次解决了"

## 使用方式

```bash
cc-feishu-bridge memory search <问题关键词>
```

示例：

```bash
cc-feishu-bridge memory search npm install failed
cc-feishu-bridge memory search python import error
cc-feishu-bridge memory search docker build
```

## 输出格式

记忆库返回格式为：

```
🔧 <问题标题>
  问题: <问题描述>
  根因: <根因分析>
  解决: <解决方案>
```

## 使用建议

- 使用中文或英文关键词均可
- 关键词越具体，返回结果越准确
- 记忆库是全局共享的，所有项目共用同一套问题记录
- 如果找到相关记忆，**直接使用返回的解决方案**，不要重复造轮子
- 如果没有找到，参考返回的提示继续自行调查

## 注意

- 记忆库搜索无需网络，在本地执行
- 只有 `problem_solution` 类型的记忆会出现在搜索结果中
- `user_preference` 和 `project_context` 类型通过系统提示词被动注入，不在此搜索范围内
"""
