"""MemorySearch tool definition and system prompt guidance for Claude SDK."""

MEMORY_SEARCH_TOOL = {
    "name": "MemorySearch",
    "description": (
        "搜索本地记忆库，查找之前遇到过的问题和解决方案。"
        "当你遇到报错、失败或不熟悉的问题时，优先使用此工具查询本地记忆库。"
        "返回结果包含问题描述、根因和已知解决方案。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "问题描述或关键词，尽量用中文描述你遇到的具体问题",
            },
            "project_path": {
                "type": "string",
                "description": "当前项目路径（可选），用于限定只搜索本项目的记忆",
            },
        },
        "required": ["query"],
    },
}

MEMORY_SYSTEM_GUIDANCE = """
当你遇到以下情况时，请优先使用 MemorySearch 工具查询本地记忆库：
- 遇到报错（error）、构建失败（build failed）、测试失败（test failed）
- 遇到之前似乎见过的问题
- 用户提到"之前也是这样"、"以前解决过"

MemorySearch 会返回本地记忆库中相关的记录，格式为【问题 + 解决方案】。
请优先参考返回的解决方案，如果不能直接解决，再自行研究。
"""