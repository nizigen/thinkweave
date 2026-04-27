"""Prompt模板加载器 — 从 prompts/{role}/{action}.md 加载Markdown模板"""

from __future__ import annotations

from pathlib import Path

from app.utils.logger import logger

# Variables that contain user-supplied content and must be sanitized
_USER_INPUT_VARS: frozenset[str] = frozenset({
    "title", "draft_text", "review_comments", "chapter_content",
    "full_text", "original_content",
})


def sanitize_prompt_variable(value: str) -> str:
    """Wrap user input in <user_input> tags and escape inner XML-like tags."""
    escaped = value.replace("<", "&lt;").replace(">", "&gt;")
    return f"<user_input>{escaped}</user_input>"


class PromptLoader:
    """
    从文件系统加载Prompt模板并渲染变量。

    模板使用 Python str.format_map() 语法：{variable_name}
    不引入 Jinja2（遵循 TECH_STACK 约束）。
    """

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        if prompts_dir is None:
            # 默认：backend/prompts/
            prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, str] = {}

    @staticmethod
    def _sanitize_segment(segment: str, name: str) -> str:
        """校验路径片段，防止路径穿越"""
        if not segment or "/" in segment or "\\" in segment or ".." in segment:
            raise ValueError(f"Invalid {name}: {segment!r}")
        return segment

    def load(self, role: str, action: str, **variables: str) -> str:
        """
        加载并渲染模板。

        1. 读取 prompts/{role}/{action}.md
        2. 用 str.format_map() 替换 {variable_name} 占位符
        3. 缺少变量时抛出 KeyError（不静默输出 {xxx}）
        """
        role = self._sanitize_segment(role, "role")
        action = self._sanitize_segment(action, "action")
        cache_key = f"{role}/{action}"

        if cache_key not in self._cache:
            path = (self.prompts_dir / role / f"{action}.md").resolve()
            if not str(path).startswith(str(self.prompts_dir.resolve())):
                raise ValueError(f"Path traversal detected: {role}/{action}")
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {path}")
            self._cache[cache_key] = path.read_text(encoding="utf-8")
            logger.debug(f"Loaded prompt template: {cache_key}")

        template = self._cache[cache_key]
        if variables:
            sanitized = {
                k: sanitize_prompt_variable(v) if k in _USER_INPUT_VARS else v
                for k, v in variables.items()
            }
            return template.format_map(sanitized)
        return template

    def load_system(self, role: str) -> str:
        """加载 prompts/{role}/system.md 作为 system message"""
        return self.load(role, "system")

    def reload(self) -> None:
        """清空缓存，强制从磁盘重新加载（debug模式用）"""
        self._cache.clear()
        logger.debug("Prompt cache cleared")
