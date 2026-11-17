# Time Tracker

一个超轻量的本地时间追踪小工具，专为"同时处理多个 case / 记 labor 不准"的场景设计。

## 在线使用与下载

- **新版网页版**：https://irishemin.github.io/timetracker/dayledger/
- **Windows 免安装版 / 离线网页版**：https://github.com/IrisHeMin/timetracker/releases/latest
- 原版网页仍保留在仓库根目录，新版位于 `dayledger` 目录。

新版网页无需登录，记录只在当前浏览器 localStorage 中保存，提供任务表、自定义分类、原生时间选择、实时饼图、HTML 日报及 JSON/CSV 导出。清理浏览器数据可能丢失记录，请定期备份。在线网页、离线 HTML 与桌面版的数据互不自动同步；JSON 备份只用于两个网页版之间迁移。

纯静态网页版不能在关闭浏览器后使用 Outlook 自动发邮件；需要此功能请下载 Windows 桌面版，在邮件设置中填写你自己的邮箱，并启用、安装计划任务。下载包不包含任何人的任务、邮箱配置或日报。Windows 程序未签名，可能提示未知发布者。

构建发布包（Windows x64，Python 3.12+）：

```powershell
python -m venv .build-venv
& .\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
& .\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name DayLedger --add-data "desktop\outlook.ps1;." --add-data "desktop\install.ps1;." desktop\launcher.py
python scripts\package-release.py
```

构建结果在被 Git 忽略的 `dist` 目录。离线网页完全内联脚本，不依赖 CDN。仅使用允许列表中的源码与构建产物打包，不读取 `%LOCALAPPDATA%\DayLedger`。

## 新增：独立桌面版 DayLedger

`desktop\app.py` 是独立的原生桌面应用，与原网页版本互不覆盖，也不会自动迁移浏览器数据。需要带 Tk 的 Python 3.10+，无第三方依赖。

- 表格记录自定义任务，内置做 case、学习、讨论、健身、娱乐；分类下拉框底部有「＋ 添加分类…」，输入名称并点击「保存分类」即可添加并自动选中，新分类会永久保留在下拉选项中。双击任务或分类修改，选择分类后立即应用到当前任务；单击 Start / Stop 下拉选择小时、分钟，确认后自动保存。新建任务同样支持添加分类、时间选择、一键选现在或清空。自定义分类自动参与饼图与邮件统计，颜色在重启后保持一致。
- 每天 09:00–17:00 内，无记录的空档归为休息；今日仅统计已经过去的工作时间。今天有 Start、尚未填 Stop 的任务暂计到当前时间（最晚 17:00），不自动修改原始 Stop；缺少 Start、未来任务或历史记录缺少 Stop 时不计入。
- 「预览日报」打开本机实时页面，每 15 秒重新读取最新记录和时间，并显示数据更新时间；应用关闭后停止更新。旧的文件预览和已发送邮件仍是生成时的快照。
- 允许并行任务，保留原始时长；饼图将重叠时段按同时进行的任务平分，避免超过实际工作时间。
- 工作日 17:00，通过已登录的经典 Outlook 发送 HTML 日报，内嵌 PNG 饼图及任务明细。
- 关闭窗口后仍由 Windows 计划任务发送；电脑需开机，用户需保持登录。离线时以 Outlook 发件箱状态为准；无法保证关机时准点发送。
- 最近 7 天漏发日报会在恢复可用或登录后补发。失败每 15 分钟重试，持续至当日 23:00；发送结果不确定时暂停重发以防重复，请检查邮件日志。

安装（不需要管理员权限）：

```powershell
& .\desktop\install.ps1 -Recipient 'your-address@example.com'
```

安装后双击桌面或开始菜单的 **DayLedger**。邮件地址与开关可在应用的「邮件设置」中修改。

任务、邮件设置及发送状态保存在 `%LOCALAPPDATA%\DayLedger\ledger.sqlite3`，日报和日志也在此目录；完整退出应用后可复制整个目录备份。本地记录不会因关闭窗口丢失。任务数据仅在生成汇总邮件时通过 Outlook 发送。

运行测试：`python -m unittest discover -s desktop -p "test_*.py"`。

停用自动发送：在邮件设置中关闭开关；彻底移除计划任务可运行 `Unregister-ScheduledTask -TaskName 'DayLedger-DailySummary' -Confirm:$false`。卸载桌面版时删除两个 DayLedger 快捷方式和 `desktop` 目录即可，原网页不受影响；本机数据需自行保留或另行删除。

## 怎么用？

### 方式 1：直接用（最快）
双击 `index.html`，浏览器打开即可。所有数据存在浏览器 localStorage 里，**只有你自己看得到**，不上传任何服务器。

### 方式 2：装成桌面 App + 全局热键（推荐）
1. 双击 `Install-TimeTracker.ps1`（或右键 → "用 PowerShell 运行"）
2. 如果弹出执行策略警告，按提示选择"以管理员身份重新运行"，或先在 PowerShell 跑：
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
3. 安装完毕后：
   - 桌面会有 **Time Tracker** 图标 → 双击打开（独立 Edge 应用窗口）
   - 任何时候按 **Ctrl + Alt + T** 都能呼出

## 功能

- ⏱ **任务计时**：输入任务名 → Start，自动记录开始/结束时间
- 🍅 **番茄钟**：可配置工作/休息时长，完成时桌面通知+提示音+标题闪烁
- 📊 **今日汇总**：按任务名分组的总时长 + 柱状图
- 📈 **趋势**：7 天 / 30 天工作-休息堆叠图，任务排行 + 占比
- 💾 **数据导入导出**：JSON / CSV，方便备份和换电脑迁移

## 注意

- 数据存在**浏览器 localStorage** 里——只在你启动它用的那个浏览器 profile 里能看到。所以快捷方式锁定用 Edge `--app` 模式打开，别用其他浏览器再打开 index.html，否则数据分家。
- 建议每周用"数据"页签里的"导出 JSON"备份一次。
- 清浏览器数据 / 重装系统会丢数据，记得提前导出。

## 卸载

删掉这个文件夹 + 桌面快捷方式 + 开始菜单里的 `Time Tracker.lnk` 即可。
