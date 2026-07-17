"""Tool 1.2: PDF 转 Word 转换器。

确定性操作，不调用 LLM。使用 pdf2docx 库实现 PDF → DOCX 转换。
如果输入本身就是 docx 则直接跳过，原样返回。
"""
from __future__ import annotations

from pathlib import Path


def pdf_to_word_converter(file_path: str) -> dict[str, object]:
    """将 PDF 简历转换为 DOCX 格式。

    使用 ``pdf2docx`` 库实现确定性转换。如果输入文件本身就是 ``.docx``，
    则直接跳过转换，原样返回成功结果。

    Parameters
    ----------
    file_path:
        PDF 或 DOCX 文件的路径。

    Returns
    -------
    dict[str, object]
        包含 ``converted_path``（转换后文件路径 str）和 ``success``（是否成功 bool）。
        对于非 PDF/DOCX 文件，返回 ``success=False``。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    # 如果输入本身就是 docx，直接跳过转换
    if suffix == ".docx":
        return {"converted_path": str(path), "success": True}

    # 非 PDF 文件无法转换
    if suffix != ".pdf":
        return {"converted_path": str(path), "success": False}

    # PDF → DOCX 转换
    converted_path = path.with_suffix(".docx")
    try:
        from pdf2docx import Converter

        converter = Converter(str(path))
        try:
            converter.convert(str(converted_path), start=0, end=None)
        finally:
            converter.close()
    except Exception:
        # 转换失败（如 pdf2docx 未安装或文件损坏）
        return {"converted_path": str(converted_path), "success": False}

    return {"converted_path": str(converted_path), "success": converted_path.exists()}
"""Tool 1.2: convert PDF resumes to DOCX when needed."""
from pathlib import Path


def pdf_to_word_converter(file_path: str) -> dict[str, object]:
    """Convert a PDF to DOCX with pdf2docx; pass DOCX through unchanged."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return {"converted_path": str(path), "success": True}
    if suffix != ".pdf":
        return {"converted_path": str(path), "success": False}

    converted_path = path.with_suffix(".docx")
    try:
        from pdf2docx import Converter

        converter = Converter(str(path))
        try:
            converter.convert(str(converted_path), start=0, end=None)
        finally:
            converter.close()
    except Exception:
        return {"converted_path": str(converted_path), "success": False}

    return {"converted_path": str(converted_path), "success": converted_path.exists()}
