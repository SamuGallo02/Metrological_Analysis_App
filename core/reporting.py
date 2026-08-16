"""
Modulo di Reporting e Statistiche Aggregate
=========================================
Elabora i risultati per la generazione di dataframe, report CSV e
statistiche aggregate per ogni singolo ID monitorato.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import pandas as pd
from core.analysis import PairResult


def detections_to_dataframe(results: List[PairResult]) -> pd.DataFrame:
    """
    Converte la lista di PairResult in un DataFrame Pandas piatto.
    Ogni riga corrisponde a una singola rilevazione.
    """
    rows = []
    for pair in results:
        for det in pair.detections:
            rows.append({
                "timestamp": pair.timestamp,
                "track_id": det.track_id if det.track_id else "N/D",
                "label": det.label,
                "confidence": det.confidence,
                "length_mm": det.length_mm,
                "width_mm": det.width_mm,
                "depth_mm": det.depth_mm if det.depth_mm is not None else float("nan"),
            })

    if not rows:
        return pd.DataFrame(columns=[
            "timestamp", "track_id", "label", "confidence", "length_mm", "width_mm", "depth_mm"
        ])

    return pd.DataFrame(rows)


def compute_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Raggruppa le rilevazioni per singolo ID (track_id) e classe (label),
    calcolando i valori MEDI di Lunghezza, Larghezza e Confidenza,
    oltre al conteggio delle apparizioni nei fotogrammi.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "ID", "Classe", "Apparizioni", "Lunghezza Media (mm)", "Larghezza Media (mm)", "Confidenza Media"
        ])

    summary_df = (
        df.groupby(["track_id", "label"])
        .agg(
            Apparizioni=("timestamp", "count"),
            Lunghezza_Media_mm=("length_mm", "mean"),
            Larghezza_Media_mm=("width_mm", "mean"),
            Confidenza_Media=("confidence", "mean"),
        )
        .reset_index()
    )

    # Arrotondamento dei valori per una resa visiva pulita
    summary_df["Lunghezza_Media_mm"] = summary_df["Lunghezza_Media_mm"].round(2)
    summary_df["Larghezza_Media_mm"] = summary_df["Larghezza_Media_mm"].round(2)
    summary_df["Confidenza_Media"] = summary_df["Confidenza_Media"].round(3)

    summary_df.rename(
        columns={
            "track_id": "ID",
            "label": "Classe",
            "Lunghezza_Media_mm": "Lunghezza Media (mm)",
            "Larghezza_Media_mm": "Larghezza Media (mm)",
            "Confidenza_Media": "Confidenza Media",
        },
        inplace=True,
    )

    return summary_df


def export_csv(df: pd.DataFrame, output_path: Union[str, Path]) -> None:
    """
    Esporta sia il dettaglio dei rilevamenti sia le statistiche aggregate per ID
    in un unico file CSV strutturato.
    """
    path = Path(output_path)
    summary_df = compute_summary(df)

    with open(path, "w", encoding="utf-8") as f:
        f.write("=== STATISTICHE AGGREGATE PER ID ===\n")
        summary_df.to_csv(f, index=False)
        f.write("\n=== DETTAGLIO RILEVAMENTI PER FOTOGRAMMA ===\n")
        df.to_csv(f, index=False)