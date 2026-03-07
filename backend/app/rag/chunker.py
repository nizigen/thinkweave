"""文本分块器 — 章节级 + 段落级分块，含重叠窗口"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """文本块"""
    content: str
    source_type: str = "chapter"    # "chapter" | "outline" | "reference"
    chapter_index: int | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        """粗略Token估算：中文字符*2"""
        return len(self.content) * 2


class TextChunker:
    """文本分块器"""

    def chunk_by_chapter(
        self, text: str, heading_pattern: str = r"^#{1,3}\s+"
    ) -> list[Chunk]:
        """
        按章节标题分割，保留章节元数据。

        Args:
            text: Markdown格式全文
            heading_pattern: 章节标题的正则匹配模式

        Returns:
            按章节分割的Chunk列表
        """
        lines = text.split("\n")
        chunks: list[Chunk] = []
        current_lines: list[str] = []
        current_index = 0
        heading_re = re.compile(heading_pattern)

        for line in lines:
            if heading_re.match(line) and current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    chunks.append(Chunk(
                        content=content,
                        source_type="chapter",
                        chapter_index=current_index,
                        metadata={"heading": current_lines[0].strip()},
                    ))
                current_lines = [line]
                current_index += 1
            else:
                current_lines.append(line)

        # Last chunk
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append(Chunk(
                    content=content,
                    source_type="chapter",
                    chapter_index=current_index,
                    metadata={"heading": current_lines[0].strip()},
                ))

        return chunks

    def chunk_by_paragraph(
        self,
        text: str,
        max_tokens: int = 500,
        overlap: int = 50,
        chapter_index: int | None = None,
    ) -> list[Chunk]:
        """
        段落级分块，带重叠窗口保持上下文连续性。

        Args:
            text: 输入文本
            max_tokens: 每块最大token数（粗略估算）
            overlap: 重叠token数
            chapter_index: 所属章节索引

        Returns:
            段落级Chunk列表
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not paragraphs:
            return []

        chunks: list[Chunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(para) * 2  # rough estimate

            if current_tokens + para_tokens > max_tokens and current_parts:
                content = "\n\n".join(current_parts)
                chunks.append(Chunk(
                    content=content,
                    source_type="chapter",
                    chapter_index=chapter_index,
                ))

                # Keep full last paragraph as overlap context
                current_parts = [current_parts[-1]]
                current_tokens = len(current_parts[0]) * 2

            current_parts.append(para)
            current_tokens += para_tokens

        # Last chunk
        if current_parts:
            content = "\n\n".join(current_parts)
            chunks.append(Chunk(
                content=content,
                source_type="chapter",
                chapter_index=chapter_index,
            ))

        return chunks
