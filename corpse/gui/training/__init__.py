"""
Training module: everything related to training a new YOLO model,
isolated in a single package. The rest of the application only knows
this entry point:

    from corpse.gui.training import TrainingPage
    page = TrainingPage(on_home=callback_to_return_home)

To work on it without opening the whole app:  python -m training

Autore: Samuele Gallo
"""

from corpse.gui.training.page import TrainingPage

__all__ = ["TrainingPage"]
