"""Image URL registry to prevent cross-chapter duplicates."""

from __future__ import annotations

import asyncio


class ImageRegistry:
    """Track image URL ownership per chapter with an async lock."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._url_to_chapter: dict[str, int] = {}
        self._chapter_to_urls: dict[int, set[str]] = {}

    async def try_register(self, chapter_index: int, url: str) -> bool:
        """Register a URL to a chapter.

        Returns True when accepted, False if this URL is already owned by a
        different chapter.
        """
        async with self._lock:
            owner = self._url_to_chapter.get(url)
            if owner is not None and owner != chapter_index:
                return False

            self._url_to_chapter[url] = chapter_index
            self._chapter_to_urls.setdefault(chapter_index, set()).add(url)
            return True

    async def urls_for_chapter(self, chapter_index: int) -> set[str]:
        async with self._lock:
            return set(self._chapter_to_urls.get(chapter_index, set()))

    async def release_chapter(self, chapter_index: int) -> None:
        async with self._lock:
            urls = self._chapter_to_urls.pop(chapter_index, set())
            for url in urls:
                self._url_to_chapter.pop(url, None)