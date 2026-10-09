"""
Application installer: detects operating system and hardware and installs ONLY
what is needed. Uses only the standard library, so it can also run with
the system Python before the virtual environment exists.

Components:
  core      - everything needed to use the app (analysis, webcam, GUI), with
              PyTorch in the best build for the hardware (CUDA if there is an NVIDIA
              GPU). Installed only once by the per-OS installers.
  training  - only the training extras (requirements-training.txt);
              never installed automatically: requested by the user from the
              training page. Also serves to repair/enable the GPU if it was missing.

Dependency checks happen here, during installation. At every launch the app only runs a quick
integrity scan of the files (integrity.py: size of each file against pip's RECORD); if something is
damaged it offers `--repair`, which reinstalls just the affected packages (see .install_state.json).

Autore: Samuele Gallo
"""
