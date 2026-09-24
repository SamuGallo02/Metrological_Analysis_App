"""
Helper di layout condiviso: centra un blocco di contenuto orizzontalmente
invece di farlo espandere su tutta la larghezza della finestra — usato da
Home, dai selettori di modalita' e dalla pagina di Training (l'Analisi
Stereo, con la sua tabella dati fitta, resta invece a piena larghezza).

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Union

from PySide6.QtWidgets import QHBoxLayout, QLayout, QWidget


def centered_content(inner: Union[QLayout, QWidget], max_width: int = 900) -> QHBoxLayout:
    """
    Avvolge un layout o un widget in un contenitore centrato orizzontalmente
    con una larghezza massima, cosi' il contenuto non si allarga a coprire
    tutta la finestra su schermi larghi. Ritorna il QHBoxLayout gia' pronto
    da aggiungere al layout della pagina chiamante.
    """
    container = QWidget()
    container.setMaximumWidth(max_width)
    if isinstance(inner, QLayout):
        container.setLayout(inner)
    else:
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(inner)
        container.setLayout(outer)

    wrapper = QHBoxLayout()
    wrapper.addStretch(1)
    wrapper.addWidget(container)
    wrapper.addStretch(1)
    return wrapper