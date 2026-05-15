"""
Advanced RAG Indexing Pipeline  —  Contextual Retrieval Edition
================================================================
인덱싱 파이프라인:

1. 문서 종류별 전략 분리
   - PDFParser  : 제목/챕터/절 구조 보존, 페이지 추적
   - ExcelParser: 시트·헤더·블록 단위 테이블 인식

2. 청킹 전 구조 보존 전처리
   - PDF  → ParsedSection(heading, content, page, level)
   - Excel → ParsedSection(heading, content, sheet, level)

3. Contextual Retrieval (Anthropic 논문 방식)
   ① Contextual Embedding
      - LLM이 청크마다 문서 맥락 설명을 생성 (gpt-4o-mini)
      - "맥락 설명 + 원본 청크" 형태로 임베딩 → 검색 정확도 향상
      - 맥락 설명은 context_cache.json으로 영속화 (doc 변경 시만 재생성)
   ② Contextual BM25
      - 맥락이 보강된 청크로 BM25 키워드 인덱스 구축
      - bm25_{doc_type}.json으로 영속화

4. 하이브리드 검색 (RRF)
   - Semantic(벡터) + BM25(키워드) 결과를 Reciprocal Rank Fusion으로 병합
   - 각 청크의 retrieval 출처(semantic/bm25/both) 메타데이터로 반환

5. 검색에 유리한 메타데이터 확장
   source, doc_type, page, sheet, section, heading_level,
   chunk_index, total_chunks, char_count, doc_hash, indexed_at,
   context_desc, contextual

6. 증분 인덱싱 (IndexManifest)
   - SHA-256 기반 변경 감지 → 변경된 파일만 재인덱싱
   - 이전 청크 ID 추적 → 스테일 청크 자동 삭제
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── 데이터 구조 ──────────────────────────────────────────────────────────────

@dataclass
class ParsedSection:
    """문서에서 추출한 의미론적 단위 (청킹 전 중간 구조)."""
    heading: str          # 섹션 제목 (없으면 빈 문자열)
    content: str          # 본문 텍스트
    page: int | None      # PDF 페이지 번호
    sheet: str | None     # Excel 시트 이름
    level: int = 0        # 제목 계층 (0=본문, 1=H1, 2=H2, ...)


@dataclass
class TextChunk:
    """ChromaDB에 저장하는 최소 단위."""
    text: str
    chunk_id: str
    metadata: dict[str, Any]


@dataclass
class IndexReport:
    """index_directory() 실행 결과 요약."""
    indexed: int = 0
    skipped: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [f"신규 {self.indexed}청크", f"변경없음 {self.skipped}건", f"삭제 {self.removed}청크"]
        if self.errors:
            parts.append(f"오류 {len(self.errors)}건")
        return " | ".join(parts)


# ── 문서 파서 (전략 분리) ─────────────────────────────────────────────────────

class DocumentParser(ABC):
    """모든 파서의 추상 기반 클래스."""

    @abstractmethod
    def can_handle(self, path: Path) -> bool: ...

    @abstractmethod
    def parse(self, path: Path) -> list[ParsedSection]: ...


class PDFParser(DocumentParser):
    """
    구조 인식 PDF 파서.
    - 제목 패턴(한국어 장/절, 번호 체계, 영문 ALL-CAPS)으로 섹션 분리
    - 짧은 섹션은 이웃 섹션과 병합해 문맥 보존
    - 페이지 번호를 각 섹션에 기록
    """

    # 한국어·영어 공통 제목 패턴 (우선순위 순서)
    _HEADING_RE: list[tuple[int, re.Pattern]] = [
        (1, re.compile(r"^(제\s*\d+\s*[장편]\s*.{1,40})$")),
        (2, re.compile(r"^(제\s*\d+\s*[절항]\s*.{1,40})$")),
        (1, re.compile(r"^(\d+\.\s+[^\d].{0,60})$")),
        (2, re.compile(r"^(\d+\.\d+\s+.{1,60})$")),
        (3, re.compile(r"^(\d+\.\d+\.\d+\s+.{1,60})$")),
        (2, re.compile(r"^(\d+\)\s+.{1,40})$")),           # 1) heading 형식
        (1, re.compile(r"^([A-Z][A-Z\s]{3,50}[A-Z])$")),  # ALL CAPS
    ]

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> list[ParsedSection]:
        try:
            import pypdf
        except ImportError:
            return []

        sections: list[ParsedSection] = []
        reader = pypdf.PdfReader(str(path))

        for page_num, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            if not raw.strip():
                continue
            raw = self._normalize_char_spaced(raw)
            sections.extend(self._split_page(raw, page_num))

        return self._merge_short_sections(sections, min_chars=100)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_char_spaced(text: str) -> str:
        """pypdf 글자별 줄바꿈 텍스트를 단어 단위로 재조합.

        'A\\nX\\n \\nC\\no\\nm\\np\\na\\ns\\ns' → 'AX Compass'
        단일 문자 비율이 50% 미만이면 원본 반환 (일반 PDF).

        공백 문자(' ')는 단어 구분자, 빈 줄('')은 문단 구분자로 처리.
        """
        lines = text.splitlines()
        non_empty = [l for l in lines if l.strip()]
        if not non_empty:
            return text
        single_ratio = sum(1 for l in non_empty if len(l.strip()) <= 1) / len(non_empty)
        if single_ratio < 0.5:
            return text

        # buf: 현재 accumulating 중인 글자들 (공백 없는 연속 글자)
        # parts: (type, value) — type은 "word" | "space" | "para"
        buf: list[str] = []
        parts: list[tuple[str, str]] = []

        def flush_buf() -> None:
            if buf:
                parts.append(("word", "".join(buf)))
                buf.clear()

        for line in lines:
            if len(line) == 0:          # 진짜 빈 줄 → 문단 구분
                flush_buf()
                parts.append(("para", ""))
            elif line.strip() == "":    # 공백만 있는 줄 → 단어 구분
                flush_buf()
                parts.append(("space", " "))
            elif len(line.strip()) == 1:  # 단일 글자
                buf.append(line.strip())
            else:                       # 여러 글자 (multi-char token)
                flush_buf()
                parts.append(("word", line.strip()))

        flush_buf()

        # parts → 최종 문자열 조합
        result: list[str] = []
        pending_space = False
        for kind, val in parts:
            if kind == "para":
                if result and result[-1] not in ("\n", "\n\n"):
                    result.append("\n\n")
                pending_space = False
            elif kind == "space":
                pending_space = True
            else:  # word
                if result and pending_space:
                    result.append(" ")
                elif result and result[-1] not in ("\n", "\n\n", " "):
                    result.append(" ")
                result.append(val)
                pending_space = False

        joined = "".join(result)
        joined = re.sub(r"  +", " ", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()

    def _split_page(self, text: str, page: int) -> list[ParsedSection]:
        """한 페이지 텍스트를 제목 기준으로 섹션 분리."""
        current_heading, current_level, buf = "", 0, []
        result: list[ParsedSection] = []

        for line in text.splitlines():
            stripped = line.strip()
            lvl = self._detect_heading_level(stripped)
            if lvl and len(stripped) < 120:
                if buf:
                    result.append(ParsedSection(current_heading, "\n".join(buf).strip(), page, None, current_level))
                current_heading, current_level, buf = stripped, lvl, []
            else:
                buf.append(line)

        if buf:
            result.append(ParsedSection(current_heading, "\n".join(buf).strip(), page, None, current_level))

        return [s for s in result if s.content.strip()]

    def _detect_heading_level(self, line: str) -> int:
        for level, pattern in self._HEADING_RE:
            if pattern.match(line):
                return level
        return 0

    def _merge_short_sections(self, sections: list[ParsedSection], min_chars: int) -> list[ParsedSection]:
        """짧은 연속 본문 섹션을 이전 섹션에 병합."""
        merged: list[ParsedSection] = []
        for s in sections:
            if merged and len(merged[-1].content) < min_chars and s.level == 0:
                prev = merged[-1]
                merged[-1] = ParsedSection(
                    prev.heading,
                    prev.content + "\n\n" + s.content,
                    prev.page,
                    prev.sheet,
                    prev.level,
                )
            else:
                merged.append(s)
        return merged


class ExcelParser(DocumentParser):
    """
    시트·테이블 인식 Excel 파서.
    - 시트 단위로 처리 → 헤더 행 자동 감지
    - 빈 행으로 구분되는 테이블 블록별로 ParsedSection 생성
    - 각 블록 상단에 헤더 행 반복 삽입으로 문맥 보존
    """

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in (".xlsx", ".xls")

    def parse(self, path: Path) -> list[ParsedSection]:
        try:
            import openpyxl
        except ImportError:
            return []

        wb = openpyxl.load_workbook(str(path), data_only=True)
        sections: list[ParsedSection] = []

        for ws in wb.worksheets:
            raw_rows = [
                [str(c.value) if c.value is not None else "" for c in row]
                for row in ws.iter_rows()
            ]
            non_empty = [r for r in raw_rows if any(c.strip() for c in r)]
            if not non_empty:
                continue

            header_row = self._detect_header(non_empty)
            blocks = self._split_blocks(raw_rows, header_row)

            for idx, block_text in enumerate(blocks, start=1):
                sections.append(ParsedSection(
                    heading=f"{ws.title} — 블록 {idx}",
                    content=block_text,
                    page=None,
                    sheet=ws.title,
                    level=1,
                ))

        return sections

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _detect_header(self, rows: list[list[str]]) -> list[str] | None:
        """첫 번째 비어있지 않은 행을 헤더로 간주."""
        return rows[0] if rows else None

    def _split_blocks(self, rows: list[list[str]], header: list[str] | None) -> list[str]:
        """빈 행 기준으로 테이블 블록 분리; 각 블록 앞에 헤더 삽입."""
        blocks: list[str] = []
        current: list[list[str]] = []

        for row in rows:
            if not any(c.strip() for c in row):
                if current:
                    blocks.append(self._rows_to_text(current, header))
                    current = []
            else:
                current.append(row)

        if current:
            blocks.append(self._rows_to_text(current, header))

        return blocks or [self._rows_to_text(rows, header)]

    def _rows_to_text(self, rows: list[list[str]], header: list[str] | None) -> str:
        lines: list[str] = []
        if header and rows and rows[0] != header:
            lines.append(" | ".join(c for c in header if c.strip()))
            lines.append("─" * 40)
        for row in rows:
            line = " | ".join(c for c in row if c.strip())
            if line.strip():
                lines.append(line)
        return "\n".join(lines)


# ── 구조 인식 청커 ────────────────────────────────────────────────────────────

class StructureAwareChunker:
    """
    ParsedSection → TextChunk 변환.

    - 섹션 제목을 각 청크 앞에 prefix로 삽입 → 검색 시 문맥 손실 방지
    - sliding-window 분할 (chunk_size / overlap 설정 가능)
    - 청크마다 검색에 유리한 메타데이터 부착
    """

    def __init__(self, chunk_size: int = 400, overlap: int = 80):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, section: ParsedSection, source: str, doc_hash: str) -> list[TextChunk]:
        if not section.content.strip():
            return []

        heading_prefix = f"[{section.heading}]\n" if section.heading else ""
        raw_chunks = self._sliding_window(section.content)
        total = len(raw_chunks)
        result: list[TextChunk] = []

        for i, raw in enumerate(raw_chunks):
            text = heading_prefix + raw
            chunk_id = _stable_id(source, section.heading, i,
                                  page=section.page or 0, sheet=section.sheet or "")
            meta = _build_metadata(
                source=source,
                section=section,
                chunk_index=i,
                total_chunks=total,
                char_count=len(text),
                doc_hash=doc_hash,
            )
            result.append(TextChunk(text=text, chunk_id=chunk_id, metadata=meta))

        return result

    def _sliding_window(self, text: str) -> list[str]:
        parts, start = [], 0
        while start < len(text):
            parts.append(text[start : start + self.chunk_size])
            start += self.chunk_size - self.overlap
        return [p for p in parts if len(p.strip()) > 50]


# ── 메타데이터 빌더 ───────────────────────────────────────────────────────────

def _stable_id(source: str, heading: str, idx: int, page: int = 0, sheet: str = "") -> str:
    """재현 가능한 청크 ID.

    heading이 비어 있는 섹션이 여러 개일 때 page/sheet로 충돌 방지.
    """
    return hashlib.md5(f"{source}::{page}::{sheet}::{heading}::{idx}".encode()).hexdigest()


def _build_metadata(
    source: str,
    section: ParsedSection,
    chunk_index: int,
    total_chunks: int,
    char_count: int,
    doc_hash: str,
) -> dict[str, Any]:
    """
    검색 필터링 및 결과 해석에 활용할 메타데이터.
    ChromaDB where 절에서 직접 필터링 가능.
    """
    doc_type = "excel" if section.sheet is not None else "pdf"
    meta: dict[str, Any] = {
        # 출처 식별
        "source": source,
        "doc_type": doc_type,
        "doc_hash": doc_hash,
        # 구조 위치
        "section": section.heading,
        "heading_level": section.level,
        # 청크 위치
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        # 품질 힌트
        "char_count": char_count,
        # 타임스탬프
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    if section.page is not None:
        meta["page"] = section.page           # PDF 페이지 번호 (필터링 가능)
    if section.sheet is not None:
        meta["sheet"] = section.sheet         # Excel 시트명 (필터링 가능)
    return meta


# ── 증분 인덱싱 매니페스트 ────────────────────────────────────────────────────

class IndexManifest:
    """
    문서별 인덱싱 상태를 JSON 파일로 영속 관리.

    manifest.json 스키마:
    {
      "/abs/path/to/file.pdf": {
        "hash": "<sha256>",
        "indexed_at": "<ISO8601>",
        "chunk_ids": ["id1", "id2", ...]
      }
    }

    사용법:
        manifest.is_changed(path)          -> 변경 여부
        manifest.get_stale_chunk_ids(path) -> 이전 청크 ID 목록 (삭제용)
        manifest.update(path, chunk_ids)   -> 성공 후 상태 저장
    """

    def __init__(self, manifest_path: Path):
        self.path = manifest_path
        self._data: dict[str, dict] = {}
        if manifest_path.exists():
            try:
                self._data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def is_changed(self, path: Path) -> bool:
        """파일이 마지막 인덱싱 이후 변경되었으면 True."""
        key = str(path)
        return key not in self._data or self._data[key]["hash"] != self._file_hash(path)

    def get_stale_chunk_ids(self, path: Path) -> list[str]:
        """이전에 인덱싱된 청크 ID 목록 반환 (재인덱싱 전 삭제에 사용)."""
        return self._data.get(str(path), {}).get("chunk_ids", [])

    def update(self, path: Path, chunk_ids: list[str]) -> None:
        """인덱싱 성공 후 상태 기록."""
        self._data[str(path)] = {
            "hash": self._file_hash(path),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "chunk_ids": chunk_ids,
        }
        self._save()

    def remove(self, path: Path) -> None:
        """삭제된 파일 항목 제거."""
        self._data.pop(str(path), None)
        self._save()

    def all_tracked_paths(self) -> list[Path]:
        return [Path(k) for k in self._data]

    # ── 내부 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── Contextual Retrieval — ① Contextual Embedding ───────────────────────────

_CONTEXT_PROMPT = """\
<document>
{doc_content}
</document>

다음은 위 문서에서 추출한 청크입니다:
<chunk>
{chunk_content}
</chunk>

이 청크가 전체 문서 내에서 어떤 위치에 있고 어떤 맥락을 담고 있는지 \
2~3문장으로 간결하게 설명하세요.
검색 성능 향상이 목적이므로 핵심 키워드를 반드시 포함하세요.
설명만 출력하고 다른 내용은 포함하지 마세요."""


class ContextualEnricher:
    """
    LLM(gpt-4o-mini)으로 청크마다 문서 맥락 설명을 생성하고 prepend.

    흐름:
        raw_chunk  →  LLM(doc_full_text, raw_chunk)  →  context_desc
        enriched_text = context_desc + "\\n\\n" + raw_chunk
        enriched_text 을 ChromaDB에 저장 → 임베딩 정확도 향상

    캐시:
        context_cache_path JSON 파일에 chunk_id 기반으로 영속화.
        동일 doc_hash 이면 LLM 재호출 없이 캐시 재사용.
    """

    def __init__(self, api_key: str, cache_path: Path, model: str = "gpt-4o-mini"):
        self._model = model
        self._cache_path = cache_path
        self._cache: dict[str, str] = {}
        self.available = False

        if cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            self.available = True
        except Exception:
            pass

    def enrich(self, doc_content: str, chunk: TextChunk) -> TextChunk:
        """청크에 맥락 설명을 prepend해 보강된 TextChunk 반환."""
        if not self.available:
            return chunk

        cache_key = chunk.chunk_id
        if cache_key not in self._cache:
            desc = self._call_llm(doc_content, chunk.text)
            self._cache[cache_key] = desc
            self._persist_cache()

        desc = self._cache[cache_key]
        if not desc:
            return chunk

        enriched_text = f"{desc}\n\n{chunk.text}"
        new_meta = {**chunk.metadata, "context_desc": desc, "contextual": True}
        return TextChunk(text=enriched_text, chunk_id=chunk.chunk_id, metadata=new_meta)

    def enrich_batch(self, doc_content: str, chunks: list[TextChunk]) -> list[TextChunk]:
        return [self.enrich(doc_content, c) for c in chunks]

    def invalidate(self, chunk_ids: list[str]) -> None:
        """재인덱싱 시 구 청크 캐시 제거."""
        for cid in chunk_ids:
            self._cache.pop(cid, None)
        self._persist_cache()

    def _call_llm(self, doc_content: str, chunk_text: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": _CONTEXT_PROMPT.format(
                        doc_content=doc_content[:6000],
                        chunk_content=chunk_text[:800],
                    ),
                }],
                max_tokens=150,
                temperature=0,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return ""

    def _persist_cache(self) -> None:
        try:
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


# ── Contextual Retrieval — ② Contextual BM25 ────────────────────────────────

class BM25Index:
    """
    맥락 보강 청크 텍스트 기반 BM25Okapi 키워드 검색 인덱스.

    - 한국어/영어 공통 정규식 토크나이저 (konlpy 불필요)
    - corpus + ids 를 JSON으로 영속화
    - search() 는 (chunk_id, bm25_score) 리스트 반환
    """

    def __init__(self) -> None:
        self._bm25: Any = None
        self._ids: list[str] = []
        self._corpus: list[list[str]] = []

    def build(self, chunk_ids: list[str], texts: list[str]) -> None:
        self._ids = list(chunk_ids)
        self._corpus = [self._tokenize(t) for t in texts]
        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(self._corpus)
        except ImportError:
            self._bm25 = None

    def search(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        """score > 0 인 결과만, score 내림차순으로 최대 k개 반환."""
        if self._bm25 is None or not self._ids:
            return []
        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            ((cid, float(sc)) for cid, sc in zip(self._ids, scores) if sc > 0),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:k]

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"ids": self._ids, "corpus": self._corpus}, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._ids    = data["ids"]
            self._corpus = data["corpus"]
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(self._corpus)
            return True
        except Exception:
            return False

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """한글 어절 + 영문/숫자 토큰 추출."""
        tokens = re.findall(r"[가-힣]+|[a-z0-9]+", text.lower())
        return tokens or [""]


# ── 하이브리드 RRF 병합 ───────────────────────────────────────────────────────

def _rrf_merge(
    semantic: list[dict[str, Any]],   # [{id, text, metadata, distance}, ...]
    bm25: list[tuple[str, float]],    # [(chunk_id, score), ...]
    semantic_w: float = 0.7,
    bm25_w: float = 0.3,
    k_rrf: int = 60,
) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion으로 두 랭킹을 병합.
    반환: [(chunk_id, rrf_score), ...] — score 내림차순
    """
    scores: dict[str, float] = {}
    for rank, hit in enumerate(semantic, 1):
        cid = hit["id"]
        scores[cid] = scores.get(cid, 0.0) + semantic_w / (k_rrf + rank)
    for rank, (cid, _) in enumerate(bm25, 1):
        scores[cid] = scores.get(cid, 0.0) + bm25_w / (k_rrf + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Hybrid Search — Cross-encoder Reranker ───────────────────────────────────

_RERANK_PROMPT = """\
검색 쿼리와 각 문서의 관련성을 0~100 사이의 정수로 평가하세요.
쿼리의 의미와 문서 내용의 의미적 일치도를 기준으로 평가합니다.
반드시 JSON 형식으로만 응답하세요: {{"scores": [점수1, 점수2, ...]}}

쿼리: {query}

{documents}"""


class LLMReranker:
    """
    GPT-4o-mini 기반 크로스-인코더 리랭커.

    동작 방식:
        RRF 병합 후 상위 후보(k * rerank_multiplier)를 단일 LLM 호출로 재평가.
        쿼리 + 모든 후보를 한 번에 전송 → 관련성 점수(0~100) 획득 → 재정렬.

    특징:
        - 단일 API 호출로 전체 후보 일괄 평가 (latency 최소화)
        - 실패 시 RRF 순서 그대로 반환 (graceful fallback)
        - 각 히트에 rerank_score(0.0~1.0) 메타데이터 추가
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self.available = False
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            self.available = True
        except Exception:
            pass

    def rerank(
        self,
        query: str,
        hits: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        히트 목록을 LLM 관련성 점수로 재정렬하고 상위 top_k 반환.
        rerank_score(float 0~1) 필드를 각 히트에 추가한다.
        """
        if not self.available or not hits:
            for h in hits:
                h.setdefault("rerank_score", None)
            return hits[:top_k]

        doc_lines = "\n\n".join(
            f"[{i + 1}] {(h.get('text') or '')[:500]}"
            for i, h in enumerate(hits)
        )
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": _RERANK_PROMPT.format(
                        query=query, documents=doc_lines
                    ),
                }],
                max_tokens=256,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw_scores: list[int] = json.loads(
                resp.choices[0].message.content
            ).get("scores", [])

            for i, h in enumerate(hits):
                h["rerank_score"] = (
                    max(0, min(100, raw_scores[i])) / 100.0
                    if i < len(raw_scores)
                    else 0.0
                )
            hits.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

        except Exception:
            for h in hits:
                h.setdefault("rerank_score", None)

        return hits[:top_k]


# ── 메인 파이프라인 ───────────────────────────────────────────────────────────

class AdvancedRAGIndexer:
    """
    고도화된 RAG 인덱싱 파이프라인.

    파서 → 청커 → ChromaDB upsert 흐름을 오케스트레이션한다.
    문서 종류(pdf/excel)마다 별도 컬렉션을 사용해 검색 전략 분리.

    기본 사용법:
        indexer = AdvancedRAGIndexer(
            api_key="sk-...",
            chroma_dir=Path("chroma_db"),
            data_dir=Path("../Data"),
        )
        report = indexer.index_directory()      # 증분 인덱싱
        report = indexer.index_directory(force=True)  # 전체 재인덱싱

        results = indexer.query("AX Compass 균형형 특성")
        results = indexer.query("실습 커리큘럼 예시", doc_types=["excel"])
        results = indexer.query("2장 내용", where={"page": 2})
    """

    # doc_type → ChromaDB 컬렉션 이름
    COLLECTION_MAP = {
        "pdf":   "adv_rag_pdf_ctx",
        "excel": "adv_rag_excel_ctx",
    }

    SUPPORTED_EXTS = {".pdf", ".xlsx", ".xls"}

    def __init__(
        self,
        api_key: str,
        chroma_dir: Path,
        data_dir: Path,
        manifest_dir: Path | None = None,
        chunk_size: int = 400,
        overlap: int = 80,
        contextual: bool = True,
        bm25_weight: float = 0.3,
        rerank: bool = True,
        rerank_multiplier: int = 3,
    ):
        self.data_dir         = data_dir
        self._chroma_dir      = chroma_dir
        self.contextual       = contextual
        self.bm25_weight      = bm25_weight
        self.rerank_multiplier = rerank_multiplier
        self.chunker  = StructureAwareChunker(chunk_size, overlap)
        self.parsers: list[DocumentParser] = [PDFParser(), ExcelParser()]
        self.manifest = IndexManifest(
            (manifest_dir or chroma_dir) / "index_manifest.json"
        )
        self._collections: dict[str, Any] = {}
        self.available = False

        # ── Contextual Embedding 인리처
        self.enricher = ContextualEnricher(
            api_key=api_key,
            cache_path=chroma_dir / "context_cache.json",
        ) if contextual else None

        # ── LLM Reranker (Hybrid Search 핵심 단계)
        self.reranker = LLMReranker(api_key=api_key) if rerank else None

        # ── BM25 인덱스 (doc_type별)
        self.bm25: dict[str, BM25Index] = {dt: BM25Index() for dt in self.COLLECTION_MAP}

        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            embed_fn = OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
            )
            client = chromadb.PersistentClient(path=str(chroma_dir))
            for doc_type, col_name in self.COLLECTION_MAP.items():
                self._collections[doc_type] = client.get_or_create_collection(
                    col_name, embedding_function=embed_fn
                )
            self.available = True
        except Exception as e:
            print(f"[AdvancedRAGIndexer] ChromaDB 초기화 실패: {e}")
            return

        # 기존 BM25 인덱스 로드
        for doc_type in self.COLLECTION_MAP:
            self.bm25[doc_type].load(chroma_dir / f"bm25_{doc_type}.json")

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def index_directory(self, force: bool = False) -> IndexReport:
        """
        data_dir 내 지원 파일을 증분 인덱싱.
        force=True 이면 변경 여부 무시하고 전체 재인덱싱.

        컬렉션이 비어 있으면 매니페스트 상태와 무관하게 자동으로 재인덱싱한다.
        (컬렉션 이름 변경 등으로 인해 비어있는 경우 자동 복구)
        """
        report = IndexReport()
        if not self.available or not self.data_dir.exists():
            report.errors.append("RAG 비활성 (chromadb 미설치 또는 data_dir 없음)")
            return report

        files = [f for f in self.data_dir.glob("*") if f.suffix.lower() in self.SUPPORTED_EXTS]
        if not files:
            report.errors.append("지원 파일 없음 (.pdf / .xlsx / .xls)")
            return report

        for path in files:
            doc_type = "pdf" if path.suffix.lower() == ".pdf" else "excel"
            col = self._collections.get(doc_type)
            collection_empty = col is not None and col.count() == 0

            # 컬렉션이 비어 있으면 force로 처리 (DB 유실 또는 컬렉션 이름 변경 대응)
            should_index = force or collection_empty or self.manifest.is_changed(path)
            if not should_index:
                report.skipped += 1
                continue
            try:
                added, removed = self._index_file(path)
                report.indexed += added
                report.removed += removed
            except Exception as e:
                report.errors.append(f"{path.name}: {e}")

        # 삭제된 파일의 스테일 청크 정리
        for tracked in self.manifest.all_tracked_paths():
            if not tracked.exists():
                self._purge_file(tracked)

        return report

    def index_file(self, path: Path) -> tuple[int, int]:
        """단일 파일 인덱싱 (added, removed) 반환."""
        return self._index_file(path)

    def query(
        self,
        query_text: str,
        doc_types: list[str] | None = None,
        k: int = 6,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        풀 파이프라인 검색:
          ① Contextual Semantic Search (ChromaDB)
          ② Contextual BM25 Search
          ③ RRF 병합  →  후보 풀 (k × rerank_multiplier)
          ④ LLM Cross-encoder Reranking  →  최종 top-k

        doc_types : ["pdf"], ["excel"], 또는 None(전체)
        where     : ChromaDB 메타데이터 필터
        반환값    : [{id, text, metadata, distance, retrieval, rrf_score, rerank_score}, ...]
                    retrieval    : "semantic" | "bm25" | "both"
                    rerank_score : float 0~1 (reranker 비활성 시 None)
        """
        if not self.available:
            return []

        targets  = doc_types or list(self.COLLECTION_MAP.keys())
        all_hits: list[dict[str, Any]] = []

        # reranker가 있으면 더 많은 후보를 RRF에서 추출해 rerank 입력으로 사용
        candidate_k = k * self.rerank_multiplier if self.reranker else k

        for doc_type in targets:
            col = self._collections.get(doc_type)
            if col is None or col.count() == 0:
                continue

            fetch_n = min(candidate_k * 2, col.count())

            # ── ① Semantic 검색
            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results":   fetch_n,
                "include":     ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            r = col.query(**kwargs)

            sem_hits: list[dict[str, Any]] = []
            sem_id_set: set[str] = set()
            for cid, doc, meta, dist in zip(
                r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]
            ):
                if doc is None:
                    continue
                sem_hits.append({"id": cid, "text": doc, "metadata": meta or {}, "distance": dist})
                sem_id_set.add(cid)

            # ── ② BM25 검색
            bm25_hits   = self.bm25[doc_type].search(query_text, k=fetch_n)
            bm25_id_set = {cid for cid, _ in bm25_hits}

            # ── ③ RRF 병합 → 후보 풀
            merged  = _rrf_merge(
                sem_hits, bm25_hits,
                semantic_w=1.0 - self.bm25_weight,
                bm25_w=self.bm25_weight,
            )
            sem_map = {h["id"]: h for h in sem_hits}
            top_ids = [cid for cid, _ in merged[:candidate_k]]

            # BM25 전용 히트 — ChromaDB에서 원문 fetch
            extra_ids = [cid for cid in top_ids if cid not in sem_map]
            if extra_ids:
                extra = col.get(ids=extra_ids, include=["documents", "metadatas"])
                for cid, doc, meta in zip(
                    extra["ids"], extra["documents"], extra["metadatas"]
                ):
                    if doc is None:
                        continue
                    sem_map[cid] = {
                        "id": cid, "text": doc, "metadata": meta or {}, "distance": 1.0,
                    }

            rrf_map = dict(merged)
            for cid in top_ids:
                if cid not in sem_map:
                    continue
                h = sem_map[cid].copy()
                in_sem  = cid in sem_id_set
                in_bm25 = cid in bm25_id_set
                h["retrieval"] = (
                    "both" if (in_sem and in_bm25) else
                    ("semantic" if in_sem else "bm25")
                )
                h["rrf_score"] = rrf_map.get(cid, 0.0)
                all_hits.append(h)

        # 전체 후보 RRF 점수 내림차순 정렬
        all_hits.sort(key=lambda x: x["rrf_score"], reverse=True)

        # ── ④ Hybrid Search — LLM Cross-encoder Reranking
        if self.reranker and self.reranker.available and all_hits:
            all_hits = self.reranker.rerank(query_text, all_hits[:candidate_k], top_k=k)
        else:
            for h in all_hits:
                h.setdefault("rerank_score", None)
            all_hits = all_hits[:k]

        return all_hits

    def collection_stats(self) -> dict[str, int]:
        """각 컬렉션의 청크 수 반환."""
        if not self.available:
            return {}
        return {dt: col.count() for dt, col in self._collections.items()}

    # ── 내부 ──────────────────────────────────────────────────────────────────

    def _index_file(self, path: Path) -> tuple[int, int]:
        """파싱 → 청킹 → (선택) Contextual Enrichment → upsert → BM25 재구축."""
        parser = next((p for p in self.parsers if p.can_handle(path)), None)
        if parser is None:
            return 0, 0

        doc_type = "pdf" if path.suffix.lower() == ".pdf" else "excel"
        col = self._collections[doc_type]

        # 1. 이전 버전 청크 삭제 + 컨텍스트 캐시 무효화
        stale_ids = self.manifest.get_stale_chunk_ids(path)
        removed = 0
        if stale_ids:
            existing = set(col.get(ids=stale_ids)["ids"])
            if existing:
                col.delete(ids=list(existing))
                removed = len(existing)
            if self.enricher:
                self.enricher.invalidate(stale_ids)

        # 2. 파싱 → 청킹
        doc_hash = self.manifest._file_hash(path)
        sections = parser.parse(path)
        raw_chunks: list[TextChunk] = []
        for section in sections:
            raw_chunks.extend(self.chunker.chunk(section, path.name, doc_hash))

        if not raw_chunks:
            self.manifest.update(path, [])
            return 0, removed

        # 3. 중복 ID 제거
        seen: set[str] = set()
        unique = [c for c in raw_chunks if not (c.chunk_id in seen or seen.add(c.chunk_id))]  # type: ignore[func-returns-value]

        # 4. ① Contextual Embedding — 문서 전체 텍스트로 맥락 생성 후 prepend
        if self.enricher and self.enricher.available:
            doc_full_text = "\n\n".join(
                (s.heading + "\n" if s.heading else "") + s.content
                for s in sections
            )
            try:
                print(f"  [Contextual] {path.name} - {len(unique)} chunks enriching...")
            except Exception:
                pass
            unique = self.enricher.enrich_batch(doc_full_text, unique)

        # 5. 배치 upsert (100건씩)
        for i in range(0, len(unique), 100):
            batch = unique[i : i + 100]
            col.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[c.metadata for c in batch],
            )

        self.manifest.update(path, [c.chunk_id for c in unique])

        # 6. ② BM25 인덱스 재구축 (전체 컬렉션 기준)
        self._rebuild_bm25(doc_type)

        return len(unique), removed

    def _rebuild_bm25(self, doc_type: str) -> None:
        """ChromaDB 컬렉션 전체 청크로 BM25 인덱스 재구축 후 저장."""
        col = self._collections.get(doc_type)
        if col is None or col.count() == 0:
            return
        result = col.get(include=["documents"])
        self.bm25[doc_type].build(result["ids"], result["documents"])
        self.bm25[doc_type].save(self._chroma_dir / f"bm25_{doc_type}.json")

    def _purge_file(self, path: Path) -> None:
        """디스크에서 삭제된 파일의 스테일 청크 제거."""
        doc_type = "pdf" if str(path).endswith(".pdf") else "excel"
        col = self._collections.get(doc_type)
        if col is None:
            return
        stale_ids = self.manifest.get_stale_chunk_ids(path)
        if stale_ids:
            existing = set(col.get(ids=stale_ids)["ids"])
            if existing:
                col.delete(ids=list(existing))
        self.manifest.remove(path)


# ── 실행 진입점 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("오류: .env 파일에 OPENAI_API_KEY가 없습니다.")
        raise SystemExit(1)

    BASE = Path(__file__).parent.parent
    indexer = AdvancedRAGIndexer(
        api_key=api_key,
        chroma_dir=BASE / "chroma_db",
        data_dir=BASE / "Data",
    )

    if not indexer.available:
        print("ChromaDB 초기화에 실패했습니다. 패키지 설치 여부를 확인하세요.")
        raise SystemExit(1)

    # ── 인덱싱 ──────────────────────────────────────────────────────────────
    print("=== 인덱싱 시작 ===")
    report = indexer.index_directory()
    print(f"결과: {report}")
    if report.errors:
        for e in report.errors:
            print(f"  오류: {e}")

    # ── 컬렉션 현황 ─────────────────────────────────────────────────────────
    stats = indexer.collection_stats()
    print("\n=== 컬렉션 현황 ===")
    for doc_type, count in stats.items():
        print(f"  {doc_type}: {count}개 청크")

    # ── 샘플 쿼리 ───────────────────────────────────────────────────────────
    total_chunks = sum(stats.values())
    if total_chunks > 0:
        sample_query = "주요 내용 요약"
        print(f"\n=== 샘플 쿼리: '{sample_query}' ===")
        results = indexer.query(sample_query, k=3)
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            src = meta.get("source", "")
            section = meta.get("section", "")
            dist = r["distance"]
            print(f"\n[{i}] {src} | {section} | 거리={dist:.4f}")
            print(r["text"][:200].replace("\n", " "), "...")
    else:
        print("\nData/ 폴더에 PDF 또는 Excel 파일을 넣고 다시 실행하세요.")
