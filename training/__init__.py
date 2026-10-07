"""
Modulo Training: tutto cio' che riguarda l'addestramento di un nuovo modello
YOLO, isolato in un unico pacchetto. Il resto dell'applicativo conosce solo
questo punto di ingresso:

    from training import TrainingPage
    page = TrainingPage(on_home=callback_per_tornare_alla_home)

Per lavorarci senza aprire l'intera app:  python -m training

Autore: Samuele Gallo
"""

from training.page import TrainingPage

__all__ = ["TrainingPage"]
