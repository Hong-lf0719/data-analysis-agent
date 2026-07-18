# -*- coding: utf-8 -*-
"""
数据加载工具

负责：读取文件 → 检测编码 → 预览结构 → 输出摘要
"""
import io
import pandas as pd
import json


def load_data(filepath: str) -> dict:
    """
    加载数据文件，自动检测编码和分隔符。
    返回：{"ok": bool, "columns": [...], "shape": [...], ...}
    """
    try:
        df = read_df(filepath)
        return {
            "ok": True,
            "encoding": "utf-8",
            "separator": ",",
            "shape": list(df.shape),
            "columns": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "head": df.head(3).to_dict(orient="records"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _decode_csv_text(filepath: str) -> str:
    """读取 CSV 字节并按 UTF-8 容错解码：遇到非法字节用 U+FFFD 替换，
    而不是像 strict 模式那样抛错、进而被回退到 latin-1 产生整列乱码。"""
    with open(filepath, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _read_csv_text(text: str, sep: str):
    """从已解码文本解析 CSV，列数 <=1 视为失败返回 None。"""
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, on_bad_lines="warn")
    except Exception:
        return None
    if df is None or len(df.columns) <= 1:
        return None
    return df


def detect_encoding_and_sep(filepath: str):
    """探测 CSV 的编码与分隔符，返回 (encoding, sep) 或 (None, None)。

    策略：优先 UTF-8（容错）——绝大多数中文 CSV 是 UTF-8，且能正确还原中文；
    仅当确实不是 UTF-8 时才回退到 GBK。绝不直接用 latin-1（会把 UTF-8 字节
    当 Latin-1 解码成 'Å§å' 这种乱码）。
    """
    text = _decode_csv_text(filepath)
    for sep in (",", "\t"):
        if _read_csv_text(text, sep) is not None:
            return "utf-8", sep

    # 回退：纯 GBK 文件
    for sep in (",", "\t"):
        try:
            df = pd.read_csv(filepath, encoding="gbk", sep=sep, on_bad_lines="warn")
            if len(df.columns) > 1:
                return "gbk", sep
        except Exception:
            continue
    return None, None


def read_df(filepath: str) -> "pd.DataFrame":
    """统一读取 CSV/Excel，自动探测编码，避免中文乱码。"""
    if filepath.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(filepath)
    enc, sep = detect_encoding_and_sep(filepath)
    if enc == "utf-8":
        df = _read_csv_text(_decode_csv_text(filepath), sep)
        if df is not None:
            return df
    if enc:
        return pd.read_csv(filepath, encoding=enc, sep=sep, on_bad_lines="warn")
    return pd.read_csv(filepath, on_bad_lines="warn")


def inspect_data(filepath: str) -> str:
    """
    生成数据的 JSON 摘要，供 LLM 分析。
    包含：形状、列名、类型、统计摘要、各区域抽样
    """
    df = read_df(filepath)

    summary = {
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "shape": list(df.shape),
        "describe": df.describe(include="all").to_dict(),
        "sample_head": df.head(3).to_dict(orient="records"),
        "sample_tail": df.tail(3).to_dict(orient="records"),
        "null_count": df.isnull().sum().to_dict(),
    }

    # 如果有分类列，按类别抽样
    categorical_cols = df.select_dtypes(include=["string", "object", "category"]).columns.tolist()
    for col in categorical_cols[:2]:  # 最多取2个分类列
        if df[col].nunique() <= 10:
            samples = {}
            for val in df[col].unique():
                subset = df[df[col] == val].head(2)
                samples[str(val)] = subset.to_dict(orient="records")
            summary[f"sample_by_{col}"] = samples

    return json.dumps(summary, ensure_ascii=False, indent=2)
