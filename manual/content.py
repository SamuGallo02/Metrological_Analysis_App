"""Manuale d'uso in inglese (lingua base). Sezioni = titoli di secondo livello (##).
Le traduzioni sono in tools/translations/<codice>.py e finiscono nel campo "manual" dei pacchetti lingua."""

MANUAL = """\
# User manual

Metrological Analysis measures real-world objects in photos and videos, using YOLO object detection and stereo \
geometry. This manual explains every part of the application.

## Getting started

When the application starts you see the sign-in window.

- **Sign in**: enter the server address, your username and your password.
- **Register**: choose the *Register* tab to create an account. New accounts are of type *User*.
- **Access key** (optional): if you have the administrator key, type it in the *Access key* field. When the key is \
correct your account becomes a **permanent administrator** of the server. After 5 wrong keys the key is locked for \
5 minutes; you can still sign in without it.
- **Continue without signing in**: use analysis and training offline, without an account. The server folders and \
your profile are not available.

After 5 wrong passwords an account is locked for 5 minutes. If the server cannot be reached, you can still sign in \
with an account you have already used on this computer: the application works in offline mode and reconnects when you \
press *Reconnect*.

## Analysis

Press **Analysis** on the home page. The analysis screen shows the **Webcam demo** button at the top (live YOLO \
detection from one or two cameras, in a separate window) and the four types of analysis below:

1. **Photo analysis** – detection and segmentation on a single photo.
2. **Stereo photo analysis** – real measurements (length, width, distance) on left/right photo pairs.
3. **Video analysis** – detection and tracking on a single video.
4. **Stereo video analysis** – detection, tracking and real measurements on a stereo video.

Choose the type you need and follow the page that opens: select the input files, check the camera settings, run the \
detection and read or export the measurements. For stereo analysis both cameras must be calibrated and the left and \
right inputs must show the same scene.

## Training

Press **Training** to train your own YOLO model.

- The first time, the application tells you that some extensions must be installed and asks for your confirmation. \
Press *Install*: a progress bar shows the installation and the application is not closed.
- If your computer has an NVIDIA graphics card, a GPU version of PyTorch (several GB) is downloaded. When the download \
ends the application restarts by itself to complete the activation.
- Keep the computer connected to the internet during the installation. If you interrupt it, the partial download is \
resumed the next time.

Trained models can be shared: see *Server folders*.

## Server folders

When you are online, the **Server folders** page shows the shared folders.

- **Photos**: you can look at, download and add photos. Please donate photos of the objects you measure.
- **YOLO models**: you can download approved models and upload yours. Uploaded models are first placed in a quarantine \
area and are published only after an administrator has checked them, because a model file can contain code.
- **Datasets**: image sets and labels used for training.

Users can read, download and add files, but cannot modify, rename or delete the existing ones: only administrators \
can. Files that already exist are never overwritten. Interrupted downloads resume from where they stopped.

## My profile

Open **My profile** from the top bar.

- **Personal data**: name, email, organization, phone and a short description. They are stored on the server and a \
copy is kept on your computer. You can also change your password here.
- **My folder on the server**: a private space that only you can see, where you can add, rename, move and delete \
files. A bar shows how much of your quota you have used.
- **Folders on this computer**: choose the folders that are offered by default when you download from, or upload \
to, the server.
- **Language**: see below.

## Languages

English is installed with the application. Open *My profile* → *Language* to download Italian, Spanish, German, \
French, Chinese (Mandarin) or Japanese. Each language is downloaded once and then works offline, and it includes this \
manual. The change is applied the next time you start the application. You can remove a language at any time.

## For administrators

Administrators open on the **Management** page, which is organised in three tabs.

- **Users**: create users, change their type (*User* or *Server*), disable or delete accounts, reset passwords, set the \
personal folder quota and read the recent activity. At least one active administrator must always remain.
- **Database**: the server folders, with full control. Models waiting in *_pending* can be approved and published \
under a new name.
- **Training**: opens the training page. Metrological analysis stays available in the bottom row.

## Troubleshooting

- **The server is unreachable**: check the address and your connection, then press *Reconnect*. You can keep working \
offline in the meantime.
- **The access key is locked**: wait for the countdown to end. Signing in without the key is always possible.
- **The training page says components are missing**: press *Install* when asked, and keep the computer online until \
the end.
- **A file cannot be uploaded**: the server accepts only certain file types in each folder, and files that already \
exist are not overwritten.
- **Not enough space in your folder**: delete files from *My folder on the server* or ask an administrator to raise \
your quota.
"""
