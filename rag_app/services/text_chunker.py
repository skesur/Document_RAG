import re
from typing import List, Dict, Any


class TextChunker:
    """
    Advanced Semantic Text Splitter that cleans document boilerplate,
    filters out Table of Contents / Disclaimers / Publisher book headers,
    and splits cleanly on sentence and paragraph boundaries.
    """

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def is_junk_or_toc(self, text: str) -> bool:
        if not text or len(text.strip()) < 30:
            return True

        lower = text.lower()

        # Heavy dots from Table of Contents (e.g., ...........)
        if text.count('...') > 3 or text.count('. . .') > 2 or text.count('.....') > 0:
            return True

        if 'disclaimer' in lower and 'unofficial free book' in lower:
            return True
        if 'table of contents' in lower and 'chapter' in lower and text.count('.') > 10:
            return True
        if 'compiled from stack overflow' in lower or 'share this pdf with anyone' in lower:
            return True
        if 'all rights reserved' in lower and len(text) < 150:
            return True

        return False

    def clean_text(self, text: str) -> str:
        """Removes common PDF headers/footers, publisher banners, and excess whitespace."""
        if not text:
            return ""
        # Remove publisher headers & footers
        cleaned = re.sub(r'GoalKicker\.com\s*[-–—]?\s*.*?\d*', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'.*?Notes for Professionals\s*\d*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'Page\s+\d+\s+of\s+\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'https?://goalkicker\.com\S*', '', cleaned, flags=re.IGNORECASE)
        # Normalize whitespace
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
        return cleaned.strip()

    def chunk_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        all_chunks = []
        global_chunk_idx = 0

        for page in pages:
            raw_text = page.get("content", "")
            text = self.clean_text(raw_text)
            page_num = page.get("page_number", 1)

            if not text or self.is_junk_or_toc(text):
                continue

            raw_chunks = self._split_text(text, self.chunk_size, self.chunk_overlap)
            for chunk_str in raw_chunks:
                clean_chunk = self.clean_text(chunk_str)
                if clean_chunk and len(clean_chunk) > 30 and not self.is_junk_or_toc(clean_chunk):
                    token_est = max(1, len(clean_chunk.split()))
                    all_chunks.append({
                        "chunk_index": global_chunk_idx,
                        "content": clean_chunk,
                        "page_number": page_num,
                        "token_count": token_est
                    })
                    global_chunk_idx += 1

        return all_chunks

    def _split_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        if len(text) <= chunk_size:
            return [text]

        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                if len(para) <= chunk_size:
                    current_chunk = para
                else:
                    sentences = re.split(r'(?<=[.?!])\s+', para)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                            current_chunk = f"{current_chunk} {sentence}" if current_chunk else sentence
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        final_chunks = []
        for ch in chunks:
            ch_clean = ch.strip()
            if ch_clean:
                final_chunks.append(ch_clean)

        return final_chunks
