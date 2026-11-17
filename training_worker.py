"""Worker that does for the server the work it cannot do itself: training, and improving photos and videos.

The server only keeps the queue (it has no GPU and no YOLO): this program, run on a computer with a graphics card,
signs in as an administrator, takes one job at a time, downloads what it needs, works, publishes the result and
says how it went. It can be stopped with Ctrl+C: the job in hand is finished first.

The improvements use the algorithm registered in `common.image_enhance`: without one, they are left in the queue.

    python training_worker.py --server https://... --user NAME --password ... [--once]

The password can also come from the AM_WORKER_PASSWORD environment variable, so it does not stay in the command.

Autore: Samuele Gallo
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from common.image_enhance import available as enhancers, improve
from common.model_metadata import build_metadata, write_metadata
from common.params import ENHANCED_DIR, JOB_DONE, JOB_FAILED
from common.paths import TRAINING_DIR
from common.remote_tree import download_tree

from corpse.functions.training.config import DEFAULT_BATCH, DEFAULT_EPOCHS, DEFAULT_IMGSZ
from corpse.functions.training.publish import publish_model
from corpse.functions.training.run import train_model
from corpse.functions.training.server_data import DATA_FILES, DATASETS_AREA
from corpse.functions.users.api import ApiClient

POLL_SECONDS = 20


def say(line: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)


def pick_device() -> str:
    """The graphics card if there is one, otherwise the processor (slow, but it works)."""
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:                                   # noqa: BLE001 - torch missing or broken: the CPU is left
        pass
    return "cpu"


def dataset_yaml(folder: Path) -> Path:
    for name in DATA_FILES:
        if (folder / name).is_file():
            return folder / name
    raise RuntimeError(f"Il dataset '{folder.name}' non ha un data.yaml.")


class Worker:
    def __init__(self, client: ApiClient, name: str, workspace: Path, device: str = ""):
        self.client, self.name = client, name
        self.workspace = Path(workspace)
        self.device = device or pick_device()

    def report(self, job_id: int, message: str, **fields: Any) -> None:
        try:
            self.client.update_training(job_id, message=message[:2000], **fields)
        except Exception as e:                          # noqa: BLE001 - the server may be unreachable for a moment
            say(f"non sono riuscito ad aggiornare il lavoro {job_id}: {e}")

    def run_job(self, job: Dict[str, Any]) -> None:
        job_id, dataset = job["id"], job["dataset"]
        say(f"lavoro {job_id}: dataset '{dataset}' per {job['username']}")
        folder = self.workspace / dataset
        self.report(job_id, "Scarico il dataset...")
        download_tree(self.client, DATASETS_AREA, dataset, folder)
        data = dataset_yaml(folder)
        self.report(job_id, f"Allenamento su {self.device}...")
        model, metrics = train_model(str(data), job["base_model"] or "yolo11n-seg.pt",
                                     int(job["epochs"] or DEFAULT_EPOCHS), int(job["imgsz"] or DEFAULT_IMGSZ),
                                     int(job["batch"] or DEFAULT_BATCH), self.device, log=say)
        write_metadata(model, build_metadata(base_model=job["base_model"], dataset_name=dataset,
                                             dataset_source="server", epochs=int(job["epochs"]),
                                             imgsz=int(job["imgsz"]), batch=int(job["batch"]), device=self.device,
                                             metrics=metrics, species=job["species"] or None,
                                             trained_by=job["username"]))
        species = job["species"] or ""
        published = ""
        if species:
            self.report(job_id, "Pubblico il modello...")
            published = publish_model(self.client, model, species)["remote"]
        self.report(job_id, "Allenamento completato.", status=JOB_DONE, model=published or model.name,
                    metrics=metrics)
        say(f"lavoro {job_id}: fatto ({published or model.name})")

    # ---- improvement of a photo or a video --------------------------------------
    def report_enhance(self, job_id: int, message: str, **fields: Any) -> None:
        try:
            self.client.update_enhance(job_id, message=message[:2000], **fields)
        except Exception as e:                          # noqa: BLE001 - the server may be unreachable for a moment
            say(f"non sono riuscito ad aggiornare il miglioramento {job_id}: {e}")

    def run_enhance(self, job: Dict[str, Any]) -> None:
        """Downloads the file, improves it and puts the copy back beside the original (`enhanced/`)."""
        job_id, area, rel = job["id"], job["area"], job["path"]
        say(f"miglioramento {job_id}: {area}/{rel} per {job['username']}")
        folder = self.workspace / "enhance" / str(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        local = folder / Path(rel).name
        self.report_enhance(job_id, "Scarico il file...")
        self.client.download(area, rel, local)
        self.report_enhance(job_id, "Miglioro l'immagine...")
        result = improve(local, job.get("method", ""), replace=True)
        parent = Path(rel).parent.as_posix()
        remote = f"{ENHANCED_DIR}/{local.name}" if parent in (".", "") else f"{parent}/{ENHANCED_DIR}/{local.name}"
        self.report_enhance(job_id, "Carico il risultato...")
        self.client.upload(area, remote, result)
        self.report_enhance(job_id, "Miglioramento completato.", status=JOB_DONE, result=remote)
        say(f"miglioramento {job_id}: fatto ({remote})")

    def one_enhance(self) -> bool:
        """Takes an improvement and does it. True if there was one."""
        if not enhancers():                             # no algorithm installed here: leave them to another worker
            return False
        job = self.client.claim_enhance(self.name)
        if not job:
            return False
        try:
            self.run_enhance(job)
        except KeyboardInterrupt:
            self.report_enhance(job["id"], "Interrotto sul computer che migliora.", status=JOB_FAILED)
            raise
        except Exception as e:                          # noqa: BLE001 - every failure goes back to who asked
            say(f"miglioramento {job['id']} non riuscito: {e}")
            traceback.print_exc()
            self.report_enhance(job["id"], str(e), status=JOB_FAILED)
        return True

    def one(self) -> bool:
        """Takes a job and runs it. True if there was one (training first, then the improvements)."""
        job = self.client.claim_training(self.name)
        if not job:
            return self.one_enhance()
        try:
            self.run_job(job)
        except KeyboardInterrupt:
            self.report(job["id"], "Interrotto sul computer che allena.", status=JOB_FAILED)
            raise
        except Exception as e:                          # noqa: BLE001 - every failure goes back to who asked
            say(f"lavoro {job['id']} non riuscito: {e}")
            traceback.print_exc()
            self.report(job["id"], str(e), status=JOB_FAILED)
        return True

    def loop(self, seconds: int = POLL_SECONDS) -> None:
        extra = f", miglioramenti: {', '.join(enhancers())}" if enhancers() else ", nessun miglioramento installato"
        say(f"in ascolto sul server, device '{self.device}'{extra} (Ctrl+C per fermarsi)")
        while True:
            try:
                if not self.one():
                    time.sleep(seconds)
            except KeyboardInterrupt:
                say("mi fermo.")
                return
            except Exception as e:                      # noqa: BLE001 - server down: wait and try again
                say(f"server non raggiungibile: {e}")
                time.sleep(seconds)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Allena i modelli e migliora le immagini che gli utenti chiedono al server")
    ap.add_argument("--server", required=True, help="indirizzo del server, es. https://nome.example.org")
    ap.add_argument("--user", required=True, help="account amministratore con cui il worker si collega")
    ap.add_argument("--password", default=os.environ.get("AM_WORKER_PASSWORD", ""))
    ap.add_argument("--name", default=f"{platform.node()}", help="nome con cui farsi riconoscere")
    ap.add_argument("--device", default="", help="0, cpu, mps... (vuoto: lo sceglie da solo)")
    ap.add_argument("--workspace", default=str(TRAINING_DIR / "server_jobs"), help="dove scaricare i dataset")
    ap.add_argument("--once", action="store_true", help="esegue un solo lavoro e termina")
    a = ap.parse_args(argv)
    if not a.password:
        say("serve la password: --password o la variabile AM_WORKER_PASSWORD")
        return 2
    client = ApiClient(a.server)
    client.login(a.user, a.password)
    worker = Worker(client, a.name, Path(a.workspace), a.device)
    if a.once:
        return 0 if worker.one() else 1
    worker.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
