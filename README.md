# Stereo Vision Analyzer — Desktop App

Applicativo desktop (Python + PySide6) per analizzare offline coppie di
immagini stereo (rx/lx): rileva e segmenta oggetti generici con modelli
YOLO11-seg (*.pt), stima le dimensioni tramite fitting ellittico + geometria
stereo ed esporta i risultati in CSV con statistiche aggregate.

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt