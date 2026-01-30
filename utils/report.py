from __future__ import annotations

from glob import glob
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple
import os
from datetime import datetime

from utils.logger import setup_logger  # PyMuPDF
logger = setup_logger(
    name='parse_logger',
    level="DEBUG",
)

def save_markdown(md_text: str, base_name: str, out_dir: str = "reports") -> str:
    os.makedirs(out_dir, exist_ok=True)
    safe = _safe_name(base_name)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(out_dir, f"{safe}-{ts}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_text)
    return path

def save_pdf_from_markdown(md_text: str, base_name: str, out_dir: str = "reports") -> Optional[str]:
    """Markdown-to-PDF using PyMuPDF with basic pagination and Unicode font.
    Ensures Cyrillic (and other) characters render by embedding a system font.
    Returns PDF path or None on failure.
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
        safe = _safe_name(base_name)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(out_dir, f"{safe}-{ts}.pdf")
        ok = _pdf_from_markdown_to_path(md_text, path)
        return path if ok else None
    except Exception:
        return None


def save_md_and_pdf(md_text: str, base_name: str, out_dir: str = "reports") -> Tuple[str, Optional[str]]:
    """Save Markdown and PDF side-by-side with the same timestamp.

    Returns: (md_path, pdf_path) where pdf_path can be None on failure.
    """
    os.makedirs(out_dir, exist_ok=True)
    safe = _safe_name(base_name)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = os.path.join(out_dir, f"{safe}-{ts}.md")
    pdf_path = os.path.join(out_dir, f"{safe}-{ts}.pdf")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
        logger.debug(f"{"Сохранен" if os.path.isfile(md_path) else 'Ошибка при сохранении'} Markdown в {md_path}")

    ok = _pdf_from_markdown_to_path(md_text, pdf_path)
    logger.debug(f"{'Сохранен' if ok else 'Ошибка при сохранении'} PDF в {pdf_path}")
    return md_path, (pdf_path if ok else None)

from pathlib import Path
def _pdf_from_markdown_to_path(markdown_text: str, output_path: str, *,
                             pdf_engine: str = "xelatex",
                             template: Optional[str] = None,
                             extra_args: Optional[list[str]] = None) -> bool:
    """
    Конвертирует Markdown с LaTeX-формулами в PDF через Pandoc (без JS).
    Требует установленный pandoc и LaTeX-движок (xelatex/tectonic/lualatex/pdflatex).

    Args:
        markdown_text: исходный Markdown (поддерживаются $...$, $$...$$, \\(...\\), \\[...\\])
        output_path: путь к итоговому PDF
        pdf_engine: xelatex | lualatex | pdflatex | tectonic
        template: путь к кастомному pandoc LaTeX-шаблону (необязательно)
        extra_args: список дополнительных аргументов pandoc (например, метаданные)

    Returns:
        True при успешной генерации PDF, False иначе.
    """
    try:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        # Проверка наличия pandoc
        pandoc = shutil.which("pandoc")
        #if not pandoc:
        #    raise FileNotFoundError("pandoc не найден в PATH")
        pandoc = 'C:\\Users\\user\\AppData\\Local\\Pandoc\\pandoc.exe'
        # Проверка наличия LaTeX-движка при выводе в PDF
        engine = shutil.which(pdf_engine)
        if not engine:
            raise FileNotFoundError(f"{pdf_engine} не найден в PATH")

        with tempfile.TemporaryDirectory() as tmp:
            md_file = Path(tmp) / "input.md"
            md_file.write_text(markdown_text, encoding="utf-8")

            cmd = [pandoc, str(md_file), "-o", str(out), "--from", "markdown+tex_math_single_backslash", "--pdf-engine", pdf_engine,
                   "--variable", "mainfont=DejaVu Serif",
                   "--variable", "sansfont=DejaVu Sans",
                   "--variable", "monofont=DejaVu Sans Mono",
                   "--variable", "lang=ru-RU",
                   '--variable', 'fontsize=10pt',
                   '--variable', 'geometry:top=2cm,bottom=2.5cm,left=2cm,right=1.5cm'
               ]

            if extra_args:
                cmd += extra_args

            subprocess.run(cmd, check=True)

        return out.is_file()
    except Exception as e:
        logger.error(f"Ошибка при конвертации Markdown в PDF: {e}")
        return False

def delete_report_files(base_name: str, out_dir: str = "reports") -> None:
    """Удаляет файлы отчета (Markdown и PDF) по заданному базовому имени."""
    md_pattern = os.path.join(out_dir, f"{_safe_name(base_name)}-*.md")
    pdf_pattern = os.path.join(out_dir, f"{_safe_name(base_name)}-*.pdf")

    for pattern in (md_pattern, pdf_pattern):
        for file in glob(pattern):
            try:
                os.remove(file)
                logger.debug(f"Удален файл: {file}")
            except Exception as e:
                logger.error(f"Ошибка при удалении файла {file}: {e}")

def _safe_name(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_", "+", ".", " ")).strip().replace(" ", "_") or "report"
