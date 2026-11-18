# Weights of the enhancement networks (not in git)

Put here, before building the Docker image or starting the web app:

- `waternet.pt` — WaterNet (Li et al. 2019), PyTorch port by tnwei/waternet (MIT). Copy it from the
  underwater-image-enhancement project (`weights/waternet.pt`).
- `funie_gan.pth` — FUnIE-GAN (Islam et al. 2020), MIT:
  `curl -L -o weights/funie_gan.pth https://raw.githubusercontent.com/xahidbuffon/FUnIE-GAN/master/PyTorch/models/funie_generator.pth`

Without them the web app works; the methods that need them show as "not installed" (open water needs WaterNet too;
fusion and classical need no weights).
