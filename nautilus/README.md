# nautilus — underwater image enhancement (core)

Copied from [nautilus-unipd/underwater-image-enhancement](https://github.com/nautilus-unipd/underwater-image-enhancement)
(the `nautilus/` package only: models, inference, metrics, video). The web app uses it in `webapp/enhance.py`;
`python -m nautilus` (command line) works here too. Fixes made in one repository must be copied to the other.

Weights (not in git): `weights/waternet.pt` and `weights/funie_gan.pth` in the project folder, or the folder set by
`NAUTILUS_WEIGHTS_DIR`. FUnIE-GAN:
`curl -L -o weights/funie_gan.pth https://raw.githubusercontent.com/xahidbuffon/FUnIE-GAN/master/PyTorch/models/funie_generator.pth`

Credits: WaterNet — Li et al., IEEE TIP 2019, PyTorch port and weights by tnwei/waternet (MIT). FUnIE-GAN — Islam et al.,
IEEE RA-L 2020, weights from xahidbuffon/FUnIE-GAN (MIT). Fusion — Ancuti et al., IEEE TIP 2018.
