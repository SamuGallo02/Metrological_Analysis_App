"""
Modulo di Reportistica e Analisi Statistica
===========================================
Fornisce le funzioni per aggregare i dati metrologici generati dall'analisi
ed esportare i report strutturati per la successiva elaborazione.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import pandas as pd
from core.analysis import ObjectDetection, PairResult


def detections_to_dataframe(results: List[PairResult]) -> pd.DataFrame:
    """Converte una lista di PairResult in un DataFrame Pandas strutturato."""
    records = []
    for res in results:
        for det in res.detections:
            records.append({
                "timestamp": det.pair_timestamp,
                "label": det.label,
                "confidence": det.confidence,
                "length_mm": det.length_mm,
                "width_mm": det.width_mm,
                "depth_mm": det.depth_mm if det.depth_mm is not None else float("nan")
            })

    return pd.DataFrame(records)


def compute_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Calcola le statistiche descrittive aggregate per ogni classe rilevata."""
    if df.empty:
        return pd.DataFrame()

    summary = df.groupby("label").agg(
        Count=("label", "count"),
        Mean_Length_mm=("length_mm", "mean"),
        Std_Length_mm=("length_mm", "std"),
        Mean_Width_mm=("width_mm", "mean"),
        Std_Width_mm=("width_mm", "std"),
        Mean_Confidence=("confidence", "mean")
    ).reset_index()

    return summary.round(3)


def export_csv(df: pd.DataFrame, output_path: Union[str, Path]) -> None:
    """Esporta il DataFrame contenente le misurazioni su file CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, sep=";", encoding="utf-8")