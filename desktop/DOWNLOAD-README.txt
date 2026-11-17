DayLedger / 时间账本

网页版：
https://irishemin.github.io/timetracker/dayledger/

Windows 免安装版：
1. 完整解压 ZIP 到固定目录，保留 DayLedger.exe 和 _internal 文件夹。
2. 双击 DayLedger.exe。无需安装 Python，不需要管理员权限。
3. 任务记录只保存在你自己的 %LOCALAPPDATA%\DayLedger 目录。
4. 需要自动日报时，进入「邮件设置」，填写你自己的邮箱，勾选自动发送，
   再点击「安装 / 修复计划任务」。需要已登录的经典 Outlook。
5. 计划任务安装后，请不要移动或删除程序文件夹；如移动，请重新安装计划任务。
6. 自动邮件要求电脑开机、Windows 用户保持登录；离线时以 Outlook 发件箱为准。
7. 程序未签名，Windows 可能提示未知发布者。源码公开，可自行审查或构建。

离线网页版：
双击 DayLedger-offline.html，不需要网络即可记录任务、查看饼图、导出日报。
清理浏览器记录可能删除数据，请定期导出 JSON 备份。
在线版、离线版和桌面版数据不自动同步，网页版备份不能直接导入桌面版。
静态网页版不能在关闭浏览器后使用 Outlook 自动发邮件，请使用桌面版。

发布包不包含作者或其他人的任务记录、邮箱设置或日报。
源码与版本：https://github.com/IrisHeMin/timetracker
