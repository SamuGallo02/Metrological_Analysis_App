"""User manual in English (base language). Sections = second-level headings (##).
Translations are in common/translations/<code>.py and end up in the "manual" field of the language packs.

Autore: Samuele Gallo
"""

MANUAL = """\
# User manual

Metrological Analysis is the desktop application of the Nautilus project (University of Padova) for measuring real-world objects, such as underwater fauna, in photos and videos. It combines YOLO object detection with stereo geometry to turn a pair of images into real lengths, widths and distances. This manual explains every part of the application.

## Getting started

When the application starts you see the welcome page.

- **Register**: choose the *Register* tab and enter a username, your email and a password. The connection to the Nautilus server is automatic: you never type an address. New accounts are of type *User*.
- **Sign in**: enter your username and password. After 5 wrong passwords the account is locked for 5 minutes.
- **Access key**: only for administrators. Press *I have an access key* and type it; when it is correct the account becomes a **permanent administrator**. After 5 wrong keys the key is locked for 5 minutes, but you can still sign in without it.
- **Continue without signing in**: use analysis and training offline, without an account. The server, the work groups and your profile are not available.
- **Language**: the language button at the top right of the welcome page and of the account bar changes the language at any time.

If the server cannot be reached, you can still sign in with an account already used on this computer: the application works offline and reconnects when you press *Reconnect*. Signing out, or changing server, never closes and reopens the application: the welcome page comes back at once.

## The way a day of work goes

The application is built around one path, and every page is a step of it.

1. **Folders**: you put in the photos, the videos or the folders you came back with, exactly as they are.
2. **Analysis**: you choose one of those folders and the model, and the analysis writes the labels of what it found.
3. **Labels**: the labels stay with the files; you look at them, correct them by hand and add the ones that were missed.
4. **Species**: a file belongs to the species its labels name, and from then on you find it under each of them.
5. **Server**: you send what is worth sharing, ask for a better image, or train a model on it.

## Your data on this computer

Everything the application saves is kept in the project folder *datasets/Dataset_Locale*, with one folder for each kind of data.

- **dataset_Foto** and **dataset_Foto_Stereo**: single photos and left/right photo pairs.
- **dataset_Video** and **dataset_Video_Stereo**: single videos and stereo videos.
- **dataset_Training**: annotated datasets used for training.
- **models**: YOLO models (.pt); the ones downloaded from the server are grouped by species.
- **labels**: the labels of the files that have none beside them, and the small previews of the photos.

The folders you add yourself are **not** copied there: they stay where they are on your disk and the application only remembers where to find them. When this computer also runs the server, the data of the server lives apart, in *datasets/server_data*.

## Folders

Press **Folders** on the home page and choose where to work: *Local*, *Server* or *Work groups*.

In **Local** you see your files on this computer, by kind, with the same tabs as the server. Photos and videos are shown **by species**: the species of a file are the classes of its labels, so a photo with two animals is under both, without being copied anywhere. The last tab, **Datasets**, holds the folders exactly as you added them, and that is where you work on them:

- **Add folder...**: registers a folder of your disk where it is. The files keep their names, labels already beside them are kept, and no naming convention is asked for.
- **Add files...**: copies chosen files into the folder that is open, label file included.
- **File under a species...**: files one or more chosen files under a species, adding a label of it. You can also do it from a species, to add a second one.
- **Remove from the list**: the application forgets a folder; the files on your disk are not touched.
- **Send to the server...**: sends a file or a whole folder to your folder on the server, or to one of your groups.

The folders registered here are the very ones the analysis offers, so a folder added in the morning can be analysed straight away.

## Labels

A label is a box or a polygon around an animal, with the name of its species. The analysis writes them, and they stay saved with the photo.

- **Labels**: the button of the views shows or hides them over the photos and the videos, previews included.
- **Create labels... / Edit labels...**: opens the editor. It says *Create* when the file has none yet.
- **In the editor**: drag a corner or a point to correct it, drag inside to move, double click (or Alt and click) on an edge to add a point, right click a point to remove it. *More points* adds one in the middle of every edge, *Box to polygon* turns a box into a shape you can mould point by point.
- **Colour**: changes the colour of the lines, for when they are hard to see over the picture. It can be one colour for all of them or one per class.
- **Improve with the server...**: asks the server for a better version of a photo or a video; when it comes back you choose whether to add it beside the original or to put it in its place (the original is kept in *originals*).

## Analysis

Press **Analysis** on the home page. At the top there is the **Webcam demo** button; below you choose one of four analyses.

1. **Photo analysis**: detection and segmentation on a single photo.
2. **Stereo photo analysis**: real measurements (length, width, distance) on left/right photo pairs.
3. **Video analysis**: detection and tracking on a single video.
4. **Stereo video analysis**: detection, tracking and real measurements on a stereo video.

On every page the steps are the same: choose the folder, choose the YOLO model, choose which objects to analyse (or *All objects*: what can be found is what the model knows), press *AVVIA ANALISI* and read the results. The folders and the models are the ones you manage in *Folders* → *Local*, so nothing is added from here. *ESPORTA CSV* saves the measurements and *Mostra solo variazioni* hides repeated rows.

Stereo analysis needs two more things. The input folder must contain the subfolders *rx* (right camera) and *lx* (left camera), as produced by the Nautilus sensing rigs: photos are named with the capture time and each video folder holds a single file. You must also enter the camera calibration, the *baseline* (distance between the two cameras, in mm) and the *focal length* (in pixels): wrong values give wrong measurements.

## Webcam demo

The webcam demo shows live YOLO detection in a separate window. Choose the mode (*Single camera* or *Live stereo (2 cameras)*), the cameras, the model and what to recognise, then press *Start*. In stereo mode the two cameras must be different devices, and at least one model must be in the *models* folder.

## Training

Press **Training** to have a YOLO model trained on an annotated dataset (a folder with a *data.yaml* file). The page opens with nothing to install, because the usual way is the first one.

- **On the server**: you ask for the training and a computer with a graphics card does the work. You see your request waiting, then running, and the trained model is published when it is done.
- **On this computer**: the training runs here, with your hardware. The components it needs (PyTorch and the training extensions, several GB with an NVIDIA card) are downloaded only when you press the button, in a small window of their own, and the application stays usable while they arrive.

A trained model is named after the species it recognises and the network it comes from, for example *Pinna_nobilis_yolo11l-seg.pt*, so its name alone says what it is.

## How good a model is

**Model performance** compares a model with the labels that were checked by hand: how many animals it finds, how many it invents, how well the boxes overlap. There is a card for each model, a comparison species by species and a test on real photos of yours, so you can see where it works and where it does not before trusting a measurement.

## The server and the work groups

When you are online, **Folders** → **Server** shows the folders shared by the laboratory computer: photos, stereo photos, videos, stereo videos, models and datasets. The *View* button switches between the folders as they are and the same files **by species**, taken from their labels.

- **Photos**: look at, download and add photos. Please donate photos of the objects you measure.
- **YOLO models**: download approved models, grouped by scientific name (for example *Pinna nobilis*). Models you upload go to quarantine and are published only after an administrator has checked them, because a model file can contain code.
- **Datasets**: image sets and labels for training. The datasets you upload are added to the server dataset.

**Work groups** are for working together. Anybody can create one and becomes its administrator: they add and remove members, promote them or step them down, and decide the settings of the group. What a member sends waits in the quarantine of the group until an administrator approves it, and a group can publish on the server in its own name. Users can read, download and add files; existing files are never overwritten and interrupted downloads resume from where they stopped.

## My profile

Open **My profile** from the top bar.

- **Personal data**: name, email, organization, phone and a short description, stored on the server. You can also change your password.
- **My folder on the server**: a private space, like a personal drive, where you add, rename, move and delete files from any of your devices. A bar shows your quota.
- **Folders on this computer**: choose the default folders for downloads and uploads.
- **Language**: choose and download a language.

## Languages

English is installed with the application. Use the language button, or *My profile* → *Language*, to download Italian, Spanish, German, French, Chinese (Mandarin) or Japanese. Each language is downloaded once, works offline and includes this manual. The change is applied the next time you start the application.

## For administrators

Administrators open on the **Management** page, which has four tabs.

- **Users**: create users, change their type (*User* or *Server*), disable or delete accounts, reset passwords, set quotas and read the recent activity. At least one active administrator must remain.
- **Database**: the server folders with full control. Models waiting in the *Awaiting approval* folder can be approved and published in their species folder; selecting a model shows its details (species, training, metrics). An administrator can also correct the labels of a photo of the server, and the view by species follows at once.
- **Photo review**: the photo submissions sent by users. Approve to publish the photos in their species folder, or reject.
- **Training**: opens the training page, where you can also download datasets from the server and publish the trained model.

The server runs on the laboratory computer. Start it with *python -m server serve* from the project folder (add *--host 0.0.0.0* to accept connections from the network), stop it with Ctrl+C, and restart it after every update of the code. The heavy work it cannot do itself - training a model, improving an image - is done by a separate worker: run *python training_worker.py* on a machine with a graphics card and it takes the requests one at a time.

## Maintenance and repair

The application checks that its libraries are intact when there is a reason to: the first time, when the installed packages change, or after a fortnight. If a file is damaged, for example after a full disk or an interrupted download, it asks to repair it: only the damaged packages are downloaded again, a progress window is shown and **no console window ever appears**. When everything is fine nothing is reinstalled and the application opens straight away.

## Troubleshooting

- **The server is unreachable**: check your connection and press *Reconnect*; you can keep working offline meanwhile.
- **"Sign-in required"**: you entered without an account; sign in to use the server and the work groups.
- **Training says components are missing**: press *Install* when asked and stay online until the end; you can keep using the application while it downloads.
- **A file cannot be uploaded**: each server folder accepts only certain file types, and existing files are not overwritten.
- **A model is rejected**: it must be inside a folder named after the scientific name, for example *Pinna nobilis*.
- **A photo is not under its species**: it has no label of that species yet; open it and use *Create labels...* or *File under a species...*.
"""
