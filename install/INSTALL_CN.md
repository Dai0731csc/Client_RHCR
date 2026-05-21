# Client 安装说明

本文说明如何在新机器上安装并启动远程理发机器人项目的 `client` 端。

## 说明范围

- 本仓库仅包含 `client` 端代码
- `cloud` 和 `server/control-side` 代码未公开
- 任何人都可以基于本项目开展学术研究
- 如需进一步讨论完整系统，或申请远端机器人控制权限，请联系 `shuai.li@oulu.fi` 或 `zhendai.huang@oulu.fi`

## 安装前准备

- Python `3.11`
- 一台带摄像头的设备，或可连接外部摄像头的电脑
- 支持 `HTTPS` 和摄像头访问的现代浏览器
- 如需云端联通能力，还需要可用的 `config/cloud.json`

## 目录位置

以下命令默认在 `client` 根目录执行。

## macOS / Linux 安装

执行：

```bash
./install/unix/bootstrap_client.sh
```

脚本会询问是否创建 `Python 3.11` 虚拟环境：

- 输入 `yes`：创建并使用 `client/.venv`
- 输入 `no`：跳过 `.venv`，直接使用系统中的 `python3.11`

安装完成后，执行环境检查：

```bash
./install/unix/verify_client.sh
```

如果你没有创建虚拟环境，可改为：

```bash
./install/unix/verify_client.sh --python python3.11
```

## Windows 安装

执行：

```powershell
.\install\windows\bootstrap_client.ps1
```

如果 PowerShell 阻止本地脚本执行，可改为：

```powershell
powershell -ExecutionPolicy Bypass -File .\install\windows\bootstrap_client.ps1
```

如果你希望跳过 `.venv`，并显式指定 Python 解释器：

```powershell
.\install\windows\bootstrap_client.ps1 -PythonExe "C:\path\to\python.exe" -Venv no
```

安装完成后，执行环境检查：

```powershell
.\install\windows\verify_client.ps1
```

如果你使用指定解释器，可改为：

```powershell
.\install\windows\verify_client.ps1 -PythonExe "C:\path\to\python.exe"
```

## 启动 client

如果使用了 `.venv`：

```bash
.venv/bin/python main.py
```

```powershell
.\.venv\Scripts\python.exe main.py
```

如果未使用 `.venv`：

```bash
python3.11 main.py
```

```powershell
py -3.11 main.py
```

服务启动后，终端会输出类似地址：

```text
HTTPS + WSS server running at https://0.0.0.0:8000
```

## 安装脚本会做什么

- 创建可选的 `client/.venv`
- 安装 `install/requirements.txt`
- 生成本地开发证书：
  - `config/certificate/local/ca.crt`
  - `config/certificate/local/cert.pem`
  - `config/certificate/local/key.pem`
- Windows 下会安装 `cryptography`，用于生成本地证书

## 首次运行注意事项

- `config/cloud.json` 不会由安装脚本自动生成
- 如果没有对应配置，云端模式下无法建立完整链路
- 启动后可访问 `https://<host>:8000/settings` 查看或修改当前传输设置
- 浏览器首次打开页面时，可能会出现本地证书告警；确认是本机服务后可继续访问

## 相关文档

- 安装入口说明：`install/README.md`
- 使用说明：`doc/USAGE_CN.md`
- 前端按钮说明：`doc/FRONTEND_BUTTON_GUIDE_CN.md`
