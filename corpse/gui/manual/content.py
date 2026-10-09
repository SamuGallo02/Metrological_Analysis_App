"""User manual in English (base language). Sections = second-level headings (##).
Translations are in tools/translations/<code>.py and end up in the "manual" field of the language packs."""

MANUAL = """\
# User manual

Metrological Analysis is the desktop application of the Nautilus project (University of Padova) for measuring real-world objects, such as underwater fauna, in photos and videos. It combines YOLO object detection with stereo geometry to turn a pair of images into real lengths, widths and distances. This manual explains every part of the application.

## Getting started

When the application starts you see the welcome page.

- **Register**: choose the *Register* tab and enter a username, your email and a password. The connection to the Nautilus server is automatic: you never type an address. New accounts are of type *User*.
- **Sign in**: enter your username and password. After 5 wrong passwords the account is locked for 5 minutes.
- **Access key**: only for administrators. Press *I have an access key* and type it; when it is correct the account becomes a **permanent administrator**. After 5 wrong keys the key is locked for 5 minutes, but you can still sign in without it.
- **Continue without signing in**: use analysis and training offline, without an account. The server folders and your profile are not available.
- **Language**: the language button at the top right of the welcome page and of the account bar changes the language at any time.

If the server cannot be reached, you can still sign in with an account already used on this computer: the application works offline and reconnects when you press *Reconnect*.

## Your data on this computer

Everything the application saves is kept in the project folder *datasets/Dataset_Locale*, with one folder for each kind of data.

- **dataset_Foto** and **dataset_Foto_Stereo**: single photos and left/right photo pairs.
- **dataset_Video** and **dataset_Video_Stereo**: single videos and stereo videos.
- **dataset_Training**: annotated datasets used for training.
- **models**: YOLO models (.pt); the ones downloaded from the server are grouped by species.
- **results**: the measurements exported as CSV.

## Analysis

Press **Analysis** on the home page. At the top there is the **Webcam demo** button; below you choose one of four analyses.

1. **Photo analysis**: detection and segmentation on a single photo.
2. **Stereo photo analysis**: real measurements (length, width, distance) on left/right photo pairs.
3. **Video analysis**: detection and tracking on a single video.
4. **Stereo video analysis**: detection, tracking and real measurements on a stereo video.

On every page the steps are the same: choose the input folder, choose the YOLO model, choose which objects to analyse (or *All objects*; the names you add must match the labels of the model), press *AVVIA ANALISI* and read the results. *ESPORTA CSV* saves the measurements in the *results* folder and *Mostra solo variazioni* hides repeated rows.

Stereo analysis needs two more things. The input folder must contain the subfolders *rx* (right camera) and *lx* (left camera), as produced by the Nautilus sensing rigs: photos are named with the capture time and each video folder holds a single file. You must also enter the camera calibration, the *baseline* (distance between the two cameras, in mm) and the *focal length* (in pixels): wrong values give wrong measurements.

## Webcam demo

The webcam demo shows live YOLO detection in a separate window. Choose the mode (*Single camera* or *Live stereo (2 cameras)*), the cameras, the model and what to recognise, then press *Start*. In stereo mode the two cameras must be different devices, and at least one model must be in the *models* folder.

## Training

Press **Training** to train your own YOLO model on an annotated dataset (a folder with a *data.yaml* file). Choose the dataset and start the local training: the console shows the progress. For heavier jobs the same page opens Google Colab.

The training components are never installed by themselves. The first time, the application asks for your confirmation and shows a progress bar. With an NVIDIA graphics card a GPU version of PyTorch (several GB) is downloaded and the application restarts by itself to complete the activation.

## Server folders

When you are online, **Server folders** shows the folders shared by the laboratory computer.

- **Photos**: look at, download and add photos. Please donate photos of the objects you measure.
- **YOLO models**: download approved models, grouped by scientific name (for example *Pinna nobilis*). Models you upload go to quarantine and are published only after an administrator has checked them, because a model file can contain code.
- **Datasets**: image sets and labels for training. The datasets you upload are added to the server dataset.

Users can read, download and add files, but only administrators can modify, rename or delete existing ones. Existing files are never overwritten, and interrupted downloads resume from where they stopped.

## My profile

Open **My profile** from the top bar.

- **Personal data**: name, email, organization, phone and a short description, stored on the server. You can also change your password.
- **My folder on the server**: a private space, like a personal drive, where you add, rename, move and delete files from any of your devices. A bar shows your quota.
- **Folders on this computer**: choose the default folders for downloads and uploads.
- **Language**: choose and download a language.

## Languages

English is installed with the application. Use the language button, or *My profile* → *Language*, to download Italian, Spanish, German, French, Chinese (Mandarin) or Japanese. Each language is downloaded once, works offline and includes this manual. The change is applied the next time you start the application.

## For administrators

Administrators open on the **Management** page, which has three tabs.

- **Users**: create users, change their type (*User* or *Server*), disable or delete accounts, reset passwords, set quotas and read the recent activity. At least one active administrator must remain.
- **Database**: the server folders with full control. Models waiting in *_pending* can be approved and published in their species folder.
- **Training**: opens the training page.

The server runs on the laboratory computer. Start it with *python -m server serve* from the project folder (add *--host 0.0.0.0* to accept connections from the network), stop it with Ctrl+C, and restart it after every update of the code.

## Maintenance and repair

At every start the application quickly checks that its libraries are intact. If a file is damaged, for example after a full disk or an interrupted download, it asks to repair it: only the damaged packages are downloaded again, a progress window is shown and no console window appears. When everything is fine nothing is reinstalled.

## Troubleshooting

- **The server is unreachable**: check your connection and press *Reconnect*; you can keep working offline meanwhile.
- **The access key is locked**: wait for the countdown; signing in without the key is always possible.
- **Training says components are missing**: press *Install* when asked and stay online until the end.
- **A file cannot be uploaded**: each server folder accepts only certain file types, and existing files are not overwritten.
- **A model is rejected**: it must be inside a folder named after the scientific name, for example *Pinna nobilis*.
- **Not enough space in your folder**: delete files or ask an administrator to raise your quota.
"""
