# 测试记录

日期：2026-11-18。环境：Windows 11 Pro 10.0.26300 x64、TOPPING E2x2 OTG；微信及 DLL 信息见 COMPATIBILITY。以下按实际执行范围记结果，后续补测保留明确证据。

## 独立音频与模拟测试

证据：`artifacts/evidence/audio-lab.json`，`tests/audio_lab.py`；只调整非默认空闲测试通道，未调整当前默认听音设备。故障注入仅结束本测试创建的挂接宿主和 AudioLab。

| ID | 类型 | 预期与实际读回 | 结果 |
|---|---|---|---|
| E01 | 独立真实音频 | 未挂接目标 scalar：1.0 → 0.97000003 | PASS |
| E02 | 独立真实音频 | 目标来源：S_OK、blocked 增加，scalar 仍为 1.0 | PASS |
| E03 | 独立真实音频 | 同进程另一返回地址：scalar 变为 0.97000003 | PASS |
| E04 | 独立真实音频 | dB setter 未被替换，读回 -1.0 dB | PASS |
| E05 | 独立真实音频 | 另一进程 scalar 调用可改变设备音量 | PASS |
| E06 | 独立真实音频 | cleanup ACK targetCount=0；卸载后目标 scalar 恢复生效 | PASS |
| E07 | 故障注入 | 安装过滤后立即抛异常，回滚 targetCount=0，目标调用恢复 | PASS |
| E08 | 故障注入 | 结束测试拥有的 Frida 宿主后，约 0.2 秒读回目标调用恢复 | PASS |
| E09 | 故障注入 | 不续期但连接仍保留；5.6 秒后 armed=false、cleaned=true、targetCount=0，目标生效 | PASS |
| E10 | 独立/模拟 | 3 次启用清理后旧 renew 均被拒绝；最后意愿/generation 另有控制器单测 | PASS（该范围） |
| E11 | 独立进程 | lab 退出并重新启动，进程创建身份变化，新进程音量调用正常 | PASS（lab，未代替 W03） |
| E12 | 独立真实音频 | 主测试端点读回 1.0、0 dB、原静音；第二测试端点也恢复 | PASS |
| B01 | 独立真实音频 | 同一来源调用第二输出端点也被阻断，确认设备范围边界 | PASS |
| B02 | 故障注入 | 过滤回调异常时原调用放行、armed=false，后续续期拒绝并可清理 | PASS |

Python 控制器单测 10 项通过：精确 profile、未知项不 attach、停用仍扫描、捕获活动等待、捕获读取失败不 attach、清理失败不报 Disabled、最终意愿/generation、微信缺失等待，以及清理失败重试不伪造确认、目标退出后解除清理锁定。

C# 设置与启动项逻辑测试 7 项通过：默认值、保存重读、原子备份、损坏重置、未知 schema、不可写路径抛错、启动项名称所有权。临时设置样本位于 artifacts/evidence，不接触用户当前设置。

## 成品工作进程与界面

证据：`artifacts/evidence/worker-smoke.json`、`ui-*.png`、`layout/results.json`。打包引擎清空 PYTHONPATH/PYTHONHOME 后启动；这证明本机无需从开发 Python 导入，不代表第二台干净 Windows 已验证。

| ID | 类型 | 实际范围 | 结果 |
|---|---|---|---|
| U01 | 原生 GUI | 首次运行防护关闭、无 Run 项、窗口可见；托盘默认开启 | PASS |
| U02 | 原生 GUI/成品引擎 | 真实 Weixin.exe 主进程与 4.2.0.53 支持项；Enabled 仅在 attach、armed 与 lease ACK 后出现 | PASS |
| U03 | GUI/文件 | 托盘设置切换后 JSON 读回，后续窗口重新读取；防护意愿也持久保存 | PASS |
| U04 | C# 文件测试 | 损坏、未知 schema、不可写路径，默认防护关闭并报告 | PASS（隔离样本） |
| U05 | 原生 GUI | 两种关闭设置可操作；正式安装版后台启动无窗口，--show 打开同一实例后仍可后台检测 | PASS（关闭时设置被用户调整的轮次未用作退出证据） |
| U06 | 原生 GUI | 主窗退出与 IPC shutdown、worker 正常清理已测；托盘三项菜单需最终复核 | PARTIAL |
| U07 | 成品 GUI/IPC | 正式安装版 --background 无窗口；--show 打开同一 PID 的窗口，无重复 worker；shutdown 确认退出 | PASS |
| U08 | 系统场景 | 不结束用户 Explorer | NOT_RUN |
| U09 | 原生/渲染 | 920×680 与 680×540 原生窗口；18 张深浅色与三缩放渲染 | PASS（未切换物理系统 DPI） |
| U10 | UI Automation | 可访问名称、复选框 Toggle 的实际副作用、按钮与 Tab 选择已测；完整键盘流程未穷尽 | PARTIAL |

## 安装和清理

安装器以普通当前用户、离线 payload、NSIS Unicode 构建。初次安装目标含中文及空格。为避免误判 NSIS 启动器提前退出，卸载以后续文件/注册表读回为准。

| ID | 类型 | 实际范围 | 结果 |
|---|---|---|---|
| I01 | 安装 EXE | 含完整自包含运行时；本机实际静默安装 exit=0，主程序/marker 存在；第二台环境缺失 | PASS（本机） |
| I02 | 安装 EXE | `artifacts/安装测试 Demo/WeixinVolumeGuard` 可启动引擎、校验微信 | PASS |
| I03 | 原生 GUI/注册表 | 自启开启后命令准确，关闭后读回不存在；测试后的外部变更保留，不猜其来源 | PASS |
| I04 | 成品 | 正式安装位置 background 启动、无主窗口，随后单实例打开并读回 Enabled | PASS |
| I05 | 安装 EXE | 正式默认位置与 payload 哈希一致；从旧开发位置启动项修正为当前安装目录 | PASS |
| I06 | 安装 EXE | 最终同版本覆盖安装 exit=0、设置保留、带 marker 的旧文件备份存在；跨历史版本及人为中断失败回退未执行 | PASS（同版本覆盖），其他 PARTIAL |
| I07 | 卸载 EXE | 已实际卸载测试目录；主 EXE、整个测试目录、卸载登记均消失 | PASS |
| I08 | 卸载 EXE | 默认保留设置、未知文件 sentinel 保留已验证；交互删除个人数据未点击 | PARTIAL |
| I09 | 注册表/文件 | 正式目录卸载后主程序、卸载登记及匹配该安装位置的 Run 全部移除 | PASS |
| I10 | 文件 | 当前成品无代码签名；未上传杀毒服务、未测试 SmartScreen 声誉 | 事实记录，不作安全认证 |

## 真实微信

| ID | 实际范围 | 结果 |
|---|---|---|
| W01 | 成品引擎就绪并等待 180 秒，未检测到录音，没有新听感反馈 | NOT_TRIGGERED |
| W02 | 没有触发新录音 | NOT_RUN |
| W03 | 未结束用户微信；自动新身份逻辑有 lab/模拟测试 | NOT_RUN（真实微信） |
| W04 | 无进程状态通过模拟测试；当前微信正在运行 | PASS（模拟），真实未运行 NOT_RUN |
| W05 | 成品引擎已实际挂接当前微信，然后停用、退出，cleanupConfirmed=true | PASS（非录音中） |
| W06 | 成品录音中途启用尚未触发，仍是关键验收缺口 | NOT_RUN |
| W07 | 没有录音中停用/退出数据 | NOT_RUN |
| W08 | 独立 lab 其他来源及其他进程调音量通过；未穷尽真实微信功能 | PARTIAL |
| W09 | 未切换用户默认设备 | NOT_RUN |
| W10 | 未休眠或重启系统音频服务 | NOT_RUN |
| W11 | 没有新连续/长录音测试 | NOT_RUN |

本测试版的成品新录音验收尚未完成，不能以 11 月 17 日原理成功记录代替 11 月 18 日成品验证。

## 工具链

.NET SDK 10.0.404 / WindowsDesktop runtime 10.0.15；CPython 3.12.10；依赖精确版本见 engine/requirements.lock.txt。Frida 17.26.4。测试原生程序由官方 Zig 0.14.1 构建。

NSIS 官方 SourceForge 下载在本机返回 HTML/连接失败，实际使用 electron-builder-binaries 维护仓库的 `nsis-3.0.4.1.7z`（编译器自报 v3.04）；源码构建脚本允许传入另一个 NSIS Unicode 编译器。下载 URL 与文件哈希保存在 artifacts/evidence/toolchain.json，不把该工具称为最新版。

测试只使用当前机器，没有第二台 Windows、真实注销登录或证书购买。所有未执行项目保留上述状态。

## 最终读回

最终安装/同版本覆盖证据：`artifacts/evidence/final-install-upgrade.json`。卸载清理/未知文件保留证据：`uninstall-readback.json`。正式安装目录的主程序集与构建 payload 哈希一致；agent SHA-256 为 `25CDCB7C481E428BA72FC8160879B992718825B3AB1F5605845BCCD36365ACC2`。

最新打包引擎在正式安装位置再次完成 Disabled → Enabled → Disabled → shutdown，cleanupConfirmed=true。正式 GUI 的背景启动和单实例已测；最后一轮窗口被最小化，后台截图未成功，未切前台恢复窗口，保留了 UIA 状态树与先前窗口/渲染截图。

维护测试前已有的防护、托盘与启动项状态均为开启；本轮维护后保留这些现有状态，并修正到正式安装位置。这不改变全新安装默认防护关闭、自启关闭的产品默认值。

安装包内测试文档是构建时的快照；本源码目录的此文件与 artifacts/evidence 是后续安装演练读回后的最新记录。
