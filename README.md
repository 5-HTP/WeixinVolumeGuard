<p align="center"><img src="src/Guard.App/Assets/App.png" width="72" alt="微信防降音助手图标"></p>
<h1 align="center">微信防降音助手</h1>

**发微信语音时，不必打断正在听的声音。**

在电脑上听歌、看视频或做音频，一按下微信语音录制，其他声音就突然变小？这个 Windows 小工具就是为了解决这件事。它阻止受支持的微信客户端在录语音时调低设备主音量，不会把音量锁在某个数值。

**[下载 Windows x64 测试版](https://github.com/5-HTP/WeixinVolumeGuard/releases/tag/v0.1.0)** · [兼容性](docs/COMPATIBILITY.md) · [问题反馈](https://github.com/5-HTP/WeixinVolumeGuard/issues)

这是独立第三方工具，与腾讯及微信官方无关。不读取聊天或语音，不上传内容，也不修改微信文件。

## 下载与使用

- **安装版 `Setup`**：适合长期使用。从开始菜单启动，可在设置里开启登录时启动。
- **免安装版 `Portable`**：下载单个 EXE，双击即可，无需手动解压。它运行时解包到临时目录，设置和日志单独保存在本机，不改动安装版的自启。

两版都无需另装 Python 或 .NET。

首页开启防护，等待显示“已启用”后再开始下一段录音。微信退出和重新启动后会重新校验。开机自启默认关闭，可以在设置中更改。关闭窗口默认保留托盘；托盘的“退出”会停用并退出。

下载包未签名。不要为运行它而关闭系统安全防护；可用发布页的 SHA-256 校验值 核对下载文件。

## 支持范围

软件首页会显示当前微信是否匹配。建议先开启防护，等显示“已启用”后再录下一条语音。

当前是测试版，对不认识的微信版本不会启用防护。成品新录音的听感、录音中途开启和更多电脑组合仍待验证。具体版本、测试范围和影响边界见[兼容性](docs/COMPATIBILITY.md)及[测试记录](docs/TEST_RESULTS.md)。

## 遇到问题？

欢迎[提 Issue](https://github.com/5-HTP/WeixinVolumeGuard/issues)，说说系统、微信版本和遇到的现象。不必贴聊天内容、录音或带个人信息的日志。也欢迎基于项目源码适配新版微信，并通过 PR 分享改动。

## 移除

在 Windows 设置“已安装的应用”中卸载，或运行安装目录的 Uninstall.exe。卸载会移除本产品启动项；个人设置和日志可选择保留。手工移动安装目录可能使启动项失效，建议重新运行安装器。

## 从源码构建

1. 安装或准备 .NET SDK 10.0.404 x64、CPython 3.12 x64、NSIS Unicode 编译器；它们仅是开发依赖。
2. 在源码目录建立 `.venv`，用 `engine/requirements.lock.txt`（如存在）或初始 `requirements.txt` 安装精确依赖。
3. 在 PowerShell 7 中执行 `./scripts/build.ps1 -DotnetExe <dotnet.exe> -NsisExe <makensis.exe> -Portable`，并在 `.tools/nsis/COPYING` 放置所用 NSIS 的许可文件。省略 `-Portable` 则只打包安装版。
4. 构建输出在 `artifacts/`；源文件、锁文件和生成的 build-manifest 共同描述构建输入。工具来源和 SHA-256 另见测试记录。

独立测试：用 Zig 0.14.1 的 `zig cc -O0 -fno-optimize-sibling-calls tests/AudioLab.c -o artifacts/AudioLab.exe -lole32` 构建 lab，再执行隔离环境中的 `tests/audio_lab.py`。脚本只允许指定空闲非默认测试通道；没有该环境就停止，不改当前听音设备。

参考与测试工具不进入生产安装包。
