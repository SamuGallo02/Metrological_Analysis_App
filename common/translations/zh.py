VERSION = 2

STRINGS = {
    "Repairing files": "正在修复文件",
    "Checking the files...": "正在检查文件...",
    "The repair did not succeed. Check your connection and free space, then restart the application.": "修复未成功。请检查网络连接和可用空间，然后重新启动应用程序。",
    "Change language": "切换语言",
    "Damaged files": "文件已损坏",
    "Some installed libraries are damaged:": "部分已安装的库已损坏：",
    "Repair them now? Only the damaged packages are downloaded again, then the app reopens by itself.": "现在修复吗？只会重新下载损坏的软件包，然后应用会自动重新打开。",
    "Enter a valid email address.": "请输入有效的电子邮件地址。",
    "No server is configured.": "尚未配置服务器。",
    "Fill in username and password.": "请填写用户名和密码。",
    "Check your connection and try again.": "请检查网络连接后重试。",
    "I have an access key (administrators)": "我有访问密钥（管理员）",
    "Scientific name": "学名",
    "Scientific name of the species (Genus species), for example {example}:": "物种学名（属名 种名），例如 {example}：",
    "Enter the scientific name as 'Genus species', for example {example}.": "请按“属名 种名”的格式输入学名，例如 {example}。",
    "Models go in a folder named after the scientific name (Genus species), for example {example}.": "模型应放在以学名（属名 种名）命名的文件夹中，例如 {example}。",
    "Publish as (path in the models folder, Genus species/file.pt):": "发布为（模型文件夹内的路径，属名 种名/文件.pt）：",
    "You can download approved models and upload new ones: an administrator checks them before publishing. Models are grouped by the scientific name of the species (Genus species).": "您可以下载已批准的模型并上传新模型：管理员会在发布前进行检查。模型按物种学名（属名 种名）分组。",
    "Stereo-photogrammetric measurement of objects with YOLO": "使用 YOLO 对物体进行立体摄影测量",
    "Measure length, width and height from stereo pairs": "通过立体图像对测量长度、宽度和高度",
    "Train your own YOLO models": "训练您自己的 YOLO 模型",
    "Share photos, models and datasets with your team": "与团队共享照片、模型和数据集",
    "<b>PyTorch with GPU support</b> ({variant}, a download of several GB) to use your {gpu} card": "<b>支持 GPU 的 PyTorch</b>（{variant}，需下载数 GB）以使用您的 {gpu} 显卡",
    "<b>the extensions required for training</b> (a few MB)": "<b>训练所需的扩展组件</b>（几 MB）",
    "A file with this name already exists (you cannot overwrite it).": "已存在同名文件（无法覆盖）。",
    "A folder with this name already exists.": "已存在同名文件夹。",
    "About me:": "个人简介：",
    "Access key:": "访问密钥：",
    "Account disabled.": "账户已被禁用。",
    "Action": "操作",
    "Active": "启用",
    "Already exists.": "已存在。",
    "Already on the server (not overwritten): {n}.": "服务器上已存在（未覆盖）：{n}。",
    "Analysis": "分析",
    "Approve": "批准",
    "Approve model": "批准模型",
    "Area reserved to administrators.": "此区域仅限管理员使用。",
    "As an administrator you can modify and delete.": "作为管理员，您可以修改和删除。",
    "At least one active administrator must remain.": "必须至少保留一名启用的管理员。",
    "Available to download": "可下载",
    "Browse...": "浏览...",
    "Cancel": "取消",
    "Cancelled (the partial file is kept to resume).": "已取消（保留未完成的文件以便续传）。",
    "Cancelled.": "已取消。",
    "Cancelling...": "正在取消...",
    "Cannot create the folder: {path}": "无法创建文件夹：{path}",
    "Change password": "修改密码",
    "Change type": "更改类型",
    "Check for languages": "检查可用语言",
    "Checking the available languages...": "正在检查可用语言...",
    "Choose a folder": "选择文件夹",
    "Choose the files to upload": "选择要上传的文件",
    "Choose the folder to upload": "选择要上传的文件夹",
    "Choose where to save": "选择保存位置",
    "Close": "关闭",
    "Components for training": "训练组件",
    "Connecting...": "正在连接...",
    "Connection interrupted during upload ({error}).": "上传过程中连接中断（{error}）。",
    "Continue without signing in (offline)": "不登录继续（离线）",
    "Could not complete the activation. Restart the application and try again from Training.": "无法完成激活。请重新启动应用，然后在“训练”中重试。",
    "Could not reach the language server: only installed languages are shown.": "无法连接语言服务器：仅显示已安装的语言。",
    "Could not start the installation.": "无法开始安装。",
    "Created": "创建时间",
    "Current password:": "当前密码：",
    "Database": "数据库",
    "Datasets": "数据集",
    "Default folders restored.": "已恢复默认文件夹。",
    "Delete": "删除",
    "Delete user {user}? The files they uploaded stay on the server.": "删除用户 {user}？该用户上传的文件将保留在服务器上。",
    "Detail": "详情",
    "Details": "详细信息",
    "Disabled": "已禁用",
    "Do you want to install them now? Stay connected to the internet.": "是否立即安装？请保持网络连接。",
    "Does not exist.": "不存在。",
    "Download": "下载",
    "Download and use": "下载并使用",
    "Download in progress: do not close this window.": "正在下载：请勿关闭此窗口。",
    "Email:": "电子邮箱：",
    "Empty file or missing size.": "文件为空或缺少大小信息。",
    "Enable/Disable": "启用/禁用",
    "English is always installed. Other languages are downloaded once and then work offline. The change is applied the next time you start the application.": "英语始终已安装。其他语言只需下载一次，之后即可离线使用。更改将在下次启动应用时生效。",
    "Error": "错误",
    "Error: {msg}": "错误：{msg}",
    "Errors:": "错误：",
    "Extension {ext} is not allowed in this area.": "此区域不允许使用扩展名 {ext}。",
    "File": "文件",
    "File not found.": "未找到文件。",
    "File too large for this area.": "文件对此区域而言过大。",
    "Folder": "文件夹",
    "Folder name:": "文件夹名称：",
    "Folder not found.": "未找到文件夹。",
    "Folders on this computer": "此计算机上的文件夹",
    "Folders saved.": "文件夹已保存。",
    "Full name:": "姓名：",
    "Incomplete download: try again to resume it.": "下载未完成：请重试以继续下载。",
    "Install": "安装",
    "Installation in progress: do not close this window.": "正在安装：请勿关闭此窗口。",
    "Installed": "已安装",
    "Internal server error.": "服务器内部错误。",
    "Invalid JSON.": "JSON 无效。",
    "Invalid access key.": "访问密钥无效。",
    "Invalid credentials.": "凭据无效。",
    "Invalid email address.": "电子邮箱地址无效。",
    "Invalid move.": "移动无效。",
    "Invalid name.": "名称无效。",
    "Invalid path.": "路径无效。",
    "Invalid quota.": "配额无效。",
    "Invalid range.": "范围无效。",
    "Invalid role.": "角色无效。",
    "Invalid server address.": "服务器地址无效。",
    "Invalid username: 3-32 characters among letters, digits, '_', '.', '-'.": "用户名无效：须为 3-32 个字符，可包含字母、数字、'_'、'.'、'-'。",
    "Invalid value for {field}.": "{field} 的值无效。",
    "Language": "语言",
    "Last sign-in": "上次登录",
    "Loading...": "正在加载...",
    "Make {user} '{role}'?": "将 {user} 设为“{role}”？",
    "Management": "管理",
    "Metrological analysis": "计量分析",
    "Missing paths.": "缺少路径。",
    "Models in <b>_pending</b> are waiting for approval.": "<b>_pending</b> 中的模型正在等待批准。",
    "Modified": "修改时间",
    "My folder": "我的文件夹",
    "My folder on the server": "我在服务器上的文件夹",
    "My profile": "我的资料",
    "Name": "名称",
    "New accounts are 'User' accounts; with the access key the account becomes a 'Server' (administrator) account.": "新账户为“用户”账户；使用访问密钥后，该账户将成为“服务器”（管理员）账户。",
    "New folder": "新建文件夹",
    "New password for {user}:": "{user} 的新密码：",
    "New password:": "新密码：",
    "New path (relative to the area):": "新路径（相对于该区域）：",
    "New user": "新建用户",
    "No account": "无账户",
    "No result.": "无结果。",
    "Not available": "不可用",
    "Not enough space in your folder (quota {mb} MB).": "您的文件夹空间不足（配额 {mb} MB）。",
    "Nothing to download (files already present).": "无需下载（文件已存在）。",
    "Offline.": "离线。",
    "Offline: list saved locally on {when}.": "离线：本地列表保存于 {when}。",
    "Offline: no saved list.": "离线：没有已保存的列表。",
    "Open": "打开",
    "Open models/_pending/<user> and select a model.": "打开 models/_pending/<user> 并选择一个模型。",
    "Open the training page": "打开训练页面",
    "Organization:": "单位：",
    "Password changed. Use the new one the next time you sign in.": "密码已修改。下次登录时请使用新密码。",
    "Password too long.": "密码过长。",
    "Password updated.": "密码已更新。",
    "Password:": "密码：",
    "Permanently delete: {names}?": "永久删除：{names}？",
    "Personal data": "个人资料",
    "Personal folder quota for {user} (MB):": "{user} 的个人文件夹配额（MB）：",
    "Phone:": "电话：",
    "Photo analysis": "照片分析",
    "Photos": "照片",
    "Preparing the list...": "正在准备列表...",
    "Profile changes need a connection to the server.": "修改资料需要连接到服务器。",
    "Profile saved.": "资料已保存。",
    "Quit": "退出",
    "Recent activity": "最近活动",
    "Reconnect": "重新连接",
    "Refresh": "刷新",
    "Register": "注册",
    "Registration is disabled: ask an administrator for an account.": "注册已关闭：请向管理员申请账户。",
    "Remove": "移除",
    "Remove the language pack?": "移除该语言包？",
    "Rename": "重命名",
    "Rename/Move": "重命名/移动",
    "Repeat new password:": "确认新密码：",
    "Repeat password:": "确认密码：",
    "Request too large.": "请求过大。",
    "Reserved to administrators.": "仅限管理员。",
    "Reset password": "重置密码",
    "Resource not found.": "未找到资源。",
    "Restore defaults": "恢复默认设置",
    "Results": "结果",
    "Save folders": "保存文件夹",
    "Save profile": "保存资料",
    "Search the manual...": "搜索手册...",
    "Select a single item.": "请只选择一项。",
    "Select a user.": "请选择一个用户。",
    "Select one or more files or folders.": "请选择一个或多个文件或文件夹。",
    "Server": "服务器",
    "Server (administrator)": "服务器（管理员）",
    "Server address missing.": "缺少服务器地址。",
    "Server folders": "服务器文件夹",
    "Server unreachable ({error}).": "无法连接服务器（{error}）。",
    "Server unreachable and no saved local access for this user.": "无法连接服务器，且此用户没有已保存的本地登录信息。",
    "Set quota": "设置配额",
    "Sign in": "登录",
    "Sign out": "退出登录",
    "Sign-in required.": "需要登录。",
    "Size": "大小",
    "Source not found.": "未找到源文件。",
    "Specify the file name.": "请指定文件名。",
    "Specify the folder name.": "请指定文件夹名称。",
    "Status": "状态",
    "Stereo photo analysis": "立体照片分析",
    "Stereo video analysis": "立体视频分析",
    "Stop the installation? The partial download will be resumed next time.": "停止安装？已下载的部分将在下次继续。",
    "The access key is not enabled on this server.": "此服务器未启用访问密钥。",
    "The application will not be closed.": "应用不会被关闭。",
    "The content does not match the declared image type.": "内容与声明的图像类型不符。",
    "The destination already exists.": "目标已存在。",
    "The file is not in quarantine.": "该文件不在隔离区中。",
    "The installation did not succeed. Check your connection and free space (see Details) and try again.": "安装未成功。请检查网络连接和可用空间（见“详细信息”），然后重试。",
    "The language will change the next time you start the application.": "语言将在下次启动应用时更改。",
    "The password must be at least {n} characters long.": "密码长度至少为 {n} 个字符。",
    "The quarantine area is protected.": "隔离区受到保护。",
    "The root of an area cannot be deleted.": "无法删除区域的根目录。",
    "The server is still unreachable.": "仍然无法连接服务器。",
    "The two passwords do not match.": "两次输入的密码不一致。",
    "This operation is available only online as an administrator.": "此操作仅限管理员在线时使用。",
    "To use training, {what} must be installed.": "要使用训练功能，必须先安装{what}。",
    "Too many attempts with the access key: try again in {minutes} min.": "访问密钥尝试次数过多：请在 {minutes} 分钟后重试。",
    "Too many attempts. Try again in {time}.": "尝试次数过多。请在 {time} 后重试。",
    "Too many attempts: try again in {minutes} min.": "尝试次数过多：请在 {minutes} 分钟后重试。",
    "Too many wrong access keys. The key is locked for {time}: you can still sign in without it.": "错误的访问密钥次数过多。密钥已被锁定 {time}：您仍可不使用密钥登录。",
    "Train new YOLO models on the server datasets and publish them in the models folder.": "使用服务器数据集训练新的 YOLO 模型，并发布到模型文件夹。",
    "Training": "训练",
    "Transfer": "传输",
    "Type": "类型",
    "Type:": "类型：",
    "Unknown area.": "未知区域。",
    "Up": "上一级",
    "Update": "更新",
    "Update available": "有可用更新",
    "Upload": "上传",
    "Upload files...": "上传文件...",
    "Upload folder...": "上传文件夹...",
    "Uploaded models are waiting for approval by an administrator.": "已上传的模型正在等待管理员批准。",
    "Use analysis and training without an account: no server folders.": "无需账户即可使用分析和训练功能：无服务器文件夹。",
    "Use this language": "使用此语言",
    "User": "用户",
    "User not found.": "未找到用户。",
    "Username already taken.": "用户名已被占用。",
    "Username:": "用户名：",
    "Users": "用户",
    "Users cannot create folders in the models area.": "用户不能在模型区域中创建文件夹。",
    "Users cannot modify or delete the server's shared files.": "用户不能修改或删除服务器的共享文件。",
    "Video analysis": "视频分析",
    "When": "时间",
    "When it finishes, the application will <b>restart by itself</b> to complete the activation (a few moments).": "完成后，应用将<b>自动重启</b>以完成激活（需几秒钟）。",
    "With the access key you become a permanent administrator of the server, even remotely.": "使用访问密钥，您将成为服务器的永久管理员，即使是远程登录也一样。",
    "With the access key you become a permanent administrator of the server.": "使用访问密钥，您将成为服务器的永久管理员。",
    "YOLO models": "YOLO 模型",
    "You are offline: the server folders are not available.": "您处于离线状态：服务器文件夹不可用。",
    "You are offline: you can see your saved data, but not change it.": "您处于离线状态：可以查看已保存的数据，但无法修改。",
    "You are using the application without an account. Sign in to create a profile and to use your personal folder on the server.": "您当前未使用账户。请登录以创建资料并使用您在服务器上的个人文件夹。",
    "You can read, download and add files; you cannot modify or delete existing ones.": "您可以查看、下载和添加文件，但不能修改或删除已有文件。",
    "You cannot delete your own account.": "您不能删除自己的账户。",
    "Your data is stored on the server and a copy is kept on this computer.": "您的数据存储在服务器上，并在此计算机上保留一份副本。",
    "Your personal folder on the server: only you can see it. You can add, rename, move and delete.": "您在服务器上的个人文件夹：只有您能看到。您可以添加、重命名、移动和删除。",
    "[WARNING] ": "[警告] ",
    "[folder] ": "[文件夹] ",
    "administrators only (optional)": "仅限管理员（可选）",
    "in use": "使用中",
    "locked: {time}": "已锁定：{time}",
    "offline": "离线",
    "online": "在线",
    "{field} is too long (max {n} characters).": "{field} 过长（最多 {n} 个字符）。",
    "{n} files downloaded.": "已下载 {n} 个文件。",
    "{n} files uploaded.": "已上传 {n} 个文件。",
    "{n} items": "{n} 项",
    "{n} users": "{n} 位用户",
    "All objects": "所有物体",
    "Camera not available": "相机不可用",
    "Camera {n}": "相机 {n}",
    "Camera:": "相机：",
    "Cameras found: {list}": "已找到相机：{list}",
    "Cameras not available": "相机不可用",
    "Choose the folders on this computer that are offered by default when you download from, or upload to, the server.": "选择在从服务器下载或向服务器上传时默认使用的此计算机上的文件夹。",
    "Choose the type of analysis": "选择分析类型",
    "Choose what you want to do": "选择您要执行的操作",
    "Could not start the demo:\n{error}": "无法启动演示：\n{error}",
    "Demo already open": "演示已打开",
    "Demo not found": "未找到演示",
    "Detection and segmentation on a single photo.": "对单张照片进行检测和分割。",
    "Detection and tracking on a single video.": "对单个视频进行检测和跟踪。",
    "Detection, tracking and real measurements on a stereo video.": "对立体视频进行检测、跟踪和真实测量。",
    "Detection, tracking and real measurements on photos and videos, single or stereo.": "对单目或立体的照片和视频进行检测、跟踪和真实测量。",
    "Error starting the demo": "启动演示时出错",
    "File not found:\n{path}": "未找到文件：\n{path}",
    "Identical cameras": "相机相同",
    "Left (L):": "左（L）：",
    "Live stereo (2 cameras)": "实时立体（2 台相机）",
    "Look at and donate photos, download and upload YOLO models and datasets.": "查看和捐赠照片，下载和上传 YOLO 模型和数据集。",
    "Looking for available cameras...": "正在查找可用相机...",
    "Mode:": "模式：",
    "No camera found": "未找到相机",
    "No camera found. Connect a webcam (built-in or USB) and reopen this window.": "未找到相机。请连接网络摄像头（内置或 USB），然后重新打开此窗口。",
    "No model": "无模型",
    "No model available": "没有可用的模型",
    "No model found in models/": "在 models/ 中未找到模型",
    "Put at least one YOLO model (.pt) in the models/ folder before starting the demo.": "启动演示前，请至少在 models/ 文件夹中放入一个 YOLO 模型（.pt）。",
    "Real measurements (length, width, distance) on left/right photo pairs.": "对左右照片对进行真实测量（长度、宽度、距离）。",
    "Right (R):": "右（R）：",
    "Select a valid YOLO model.": "请选择有效的 YOLO 模型。",
    "Select a valid camera.": "请选择有效的相机。",
    "Select two valid cameras.": "请选择两台有效的相机。",
    "Single camera": "单相机",
    "Start": "开始",
    "Starts live YOLO detection from the webcam in a separate window.": "在单独的窗口中使用网络摄像头启动实时 YOLO 检测。",
    "The left and right cameras must be two different devices.": "左右相机必须是两台不同的设备。",
    "The webcam demo is already running: look for it among the open windows (it may be behind this one), or close it before opening another.": "网络摄像头演示已在运行：请在已打开的窗口中查找（可能在此窗口后面），或先关闭它再打开新的。",
    "Train a new YOLO model on an annotated dataset.": "使用已标注的数据集训练新的 YOLO 模型。",
    "User manual": "用户手册",
    "Webcam demo — settings": "网络摄像头演示 — 设置",
    "What to recognise:": "识别对象：",
    "YOLO model:": "YOLO 模型：",
    "a second camera is needed for stereo mode.": "立体模式需要第二台相机。",
    "← Back to home": "← 返回主页",
    "🎥 Webcam demo": "🎥 网络摄像头演示",
}

MANUAL = """\
# 用户手册

计量分析是 Nautilus 项目（帕多瓦大学）的桌面应用程序，用于在照片和视频中测量真实物体，例如水下生物。它将 YOLO 目标检测与立体几何相结合，把一对图像转换为真实的长度、宽度和距离。本手册介绍应用程序的每个部分。

## 开始使用

启动应用程序时会看到欢迎页面。

- **注册**：选择*注册*标签，输入用户名、电子邮件和密码。与 Nautilus 服务器的连接是自动的：您无需输入任何地址。新账户的类型为*用户*。
- **登录**：输入用户名和密码。密码错误 5 次后，账户将被锁定 5 分钟。
- **访问密钥**：仅限管理员。点击*我有访问密钥*并输入；密钥正确时，账户将成为**永久管理员**。密钥错误 5 次后将被锁定 5 分钟，但您仍可不使用密钥登录。
- **不登录继续**：无需账户，离线使用分析和训练。服务器文件夹和您的个人资料不可用。
- **语言**：欢迎页面和账户栏右上角的语言按钮可随时切换语言。

如果无法连接服务器，您仍可使用此电脑上已用过的账户登录：应用程序以离线模式运行，点击*重新连接*后会重新联网。

## 此电脑上的数据

应用程序保存的所有内容都位于项目文件夹 *datasets/Dataset_Locale* 中，每种数据对应一个文件夹。

- **dataset_Foto** 和 **dataset_Foto_Stereo**：单张照片和左右照片对。
- **dataset_Video** 和 **dataset_Video_Stereo**：单个视频和立体视频。
- **dataset_Training**：用于训练的已标注数据集。
- **models**：YOLO 模型（.pt）；从服务器下载的模型按物种分组。
- **results**：导出为 CSV 的测量结果。

## 分析

在主页点击**分析**。顶部是**网络摄像头演示**按钮；下方可选择四种分析之一。

1. **照片分析**：对单张照片进行检测和分割。
2. **立体照片分析**：对左右照片对进行真实测量（长度、宽度、距离）。
3. **视频分析**：对单个视频进行检测和跟踪。
4. **立体视频分析**：对立体视频进行检测、跟踪和真实测量。

每个页面的步骤相同：选择输入文件夹，选择 YOLO 模型，选择要分析的物体（或*所有物体*；添加的名称必须与模型的标签一致），点击*AVVIA ANALISI*并查看结果。*ESPORTA CSV* 会把测量结果保存到 *results* 文件夹，*Mostra solo variazioni* 会隐藏重复的行。

立体分析还需要两项内容。输入文件夹必须包含子文件夹 *rx*（右相机）和 *lx*（左相机），与 Nautilus 传感装置生成的一致：照片以拍摄时间命名，每个视频文件夹只含一个文件。您还必须输入相机标定参数，即*基线*（两个相机之间的距离，单位毫米）和*焦距*（单位像素）：数值错误会导致测量错误。

## 网络摄像头演示

网络摄像头演示在单独的窗口中实时显示 YOLO 检测。选择模式（*单相机*或*实时立体（2 个相机）*）、相机、模型以及要识别的对象，然后点击*开始*。在立体模式下，两个相机必须是不同的设备，并且 *models* 文件夹中至少要有一个模型。

## 训练

点击**训练**，可在已标注的数据集（含 *data.yaml* 文件的文件夹）上训练您自己的 YOLO 模型。选择数据集并开始本地训练：控制台会显示进度。对于更繁重的任务，同一页面可打开 Google Colab。

训练组件不会自行安装。首次使用时，应用程序会请求您确认并显示进度条。如果有 NVIDIA 显卡，将下载支持 GPU 的 PyTorch（数 GB），应用程序会自行重启以完成激活。

## 服务器文件夹

联网时，**服务器文件夹**会显示实验室电脑共享的文件夹。

- **照片**：查看、下载和添加照片。请捐赠您所测量物体的照片。
- **YOLO 模型**：下载已批准的模型，按学名分组（例如 *Pinna nobilis*）。您上传的模型会进入隔离区，经管理员检查后才会发布，因为模型文件可能包含代码。
- **数据集**：用于训练的图像和标签集合。您上传的数据集会被加入服务器数据集。

用户可以读取、下载和添加文件，但只有管理员可以修改、重命名或删除现有文件。现有文件不会被覆盖，中断的下载会从中断处继续。

## 我的个人资料

从顶部栏打开**我的个人资料**。

- **个人资料**：姓名、电子邮件、机构、电话和简短介绍，保存在服务器上。您也可以在此修改密码。
- **我在服务器上的文件夹**：一个私人空间，类似个人云盘，您可在任意设备上添加、重命名、移动和删除文件。进度条显示您的配额。
- **此电脑上的文件夹**：选择下载和上传的默认文件夹。
- **语言**：选择并下载语言。

## 语言

英语随应用程序一起安装。使用语言按钮，或*我的个人资料* → *语言*，可下载意大利语、西班牙语、德语、法语、中文（普通话）或日语。每种语言只需下载一次，可离线使用，并包含本手册。更改将在下次启动应用程序时生效。

## 管理员

管理员打开**管理**页面，其中有三个标签。

- **用户**：创建用户、更改类型（*用户*或*服务器*）、停用或删除账户、重置密码、设置配额并查看最近活动。必须至少保留一名活跃的管理员。
- **数据库**：拥有完全控制权的服务器文件夹。*_pending* 中等待的模型可以被批准并发布到其物种文件夹中。
- **训练**：打开训练页面。

服务器运行在实验室电脑上。在项目文件夹中用 *python -m server serve* 启动它（添加 *--host 0.0.0.0* 以接受来自网络的连接），用 Ctrl+C 停止，并在每次代码更新后重新启动。

## 维护与修复

每次启动时，应用程序都会快速检查其库是否完好。如果某个文件已损坏，例如磁盘已满或下载中断之后，它会请求修复：只会重新下载损坏的软件包，显示进度窗口，并且不会出现控制台窗口。一切正常时不会重新安装任何内容。

## 故障排除

- **无法连接服务器**：检查网络连接并点击*重新连接*；期间您可以继续离线工作。
- **访问密钥被锁定**：等待倒计时结束；不使用密钥始终可以登录。
- **训练提示缺少组件**：出现提示时点击*安装*，并保持联网直到结束。
- **文件无法上传**：每个服务器文件夹只接受特定类型的文件，现有文件不会被覆盖。
- **模型被拒绝**：它必须位于以学名命名的文件夹中，例如 *Pinna nobilis*。
- **您的文件夹空间不足**：删除文件，或请管理员提高您的配额。
"""
