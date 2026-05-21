# Client 使用说明

本文说明远程理发机器人项目 `client` 端的基本使用方式。内容聚焦于启动服务、访问页面、完成前端操作，以及进入正常工作流程前的准备步骤。

## 说明范围

- 本仓库仅包含 `client` 端代码
- `cloud` 和 `server/control-side` 代码未公开
- 本说明不包含远端机器人控制权限的授予流程
- 如需进一步讨论完整系统，或申请远端机器人控制权限，请联系 `shuai.li@oulu.fi` 或 `zhendai.huang@oulu.fi`

## 1. 启动服务

在 `client` 根目录启动程序：

```bash
.venv/bin/python main.py
```

或：

```bash
python3.11 main.py
```

Windows 下可使用：

```powershell
.\.venv\Scripts\python.exe main.py
```

服务启动后，默认监听：

- `https://<host>:8000/`
- `https://<host>:8000/settings`

## 2. 找到运行机器的 IP

如果你要在手机、平板或另一台电脑上访问前端页面，需要先找到运行 `client` 的机器 IP。

- Windows：执行 `ipconfig`
- macOS：执行 `ifconfig`
- Linux：执行 `ip addr` 或 `hostname -I`

通常应使用当前网络接口对应的 IPv4 地址，例如 `192.168.1.23`。

## 3. 打开页面

在浏览器中访问：

- 相机页：`https://<电脑IP>:8000/`
- 设置页：`https://<电脑IP>:8000/settings`

首次访问可能遇到本地 HTTPS 证书提醒。确认访问的是你自己的 `client` 服务后，可继续打开页面。

## 4. 推荐使用流程

建议按下面顺序操作：

1. 启动 `client`
2. 打开设置页，确认当前传输模式、`session_id`、`cloud_host`、本地拓扑是否正确
3. 打开相机页
4. 点击 `Open rear camera`
5. 点击 `Time sync`
6. 如设备尚未完成相机标定，执行 `Camera calibration`
7. 执行 `Initial calibration`
8. 点击 `Start continuous detection`
9. 如需要，使用 `Open gripper / Close gripper`

## 5. 设置页说明

设置页用于调整运行中的传输配置。页面修改会自动生效，不需要单独点击保存。

重点项目如下：

- `Transport Mode`：选择 `local_udp`、`local_tcp`、`cloud_tcp`、`cloud_udp` 之一
- `Session ID`：云端会话标识
- `Cloud Host`：云端 relay 主机地址
- `Local Topology`：`same_machine` 或 `same_lan`

注意：

- `client` 与控制端 `server` 的传输模式必须一致
- 云端模式下，双方通常还需要一致的 `session_id`
- 如果没有可用的云端配置，相关云端链路无法正常工作

## 6. 相机页说明

相机页负责前端采集、标定和连续检测。常见操作为：

- `Open rear camera`：打开后置摄像头
- `Camera calibration`：采集棋盘格图像并计算相机内参
- `Time sync`：完成浏览器与后端时间同步
- `Initial calibration`：采集 AprilTag 初始参考位姿
- `Start continuous detection`：持续检测并上报 AprilTag 数据
- `Open gripper / Close gripper`：发送夹爪开合命令

## 7. 典型使用场景

### 首次在新设备上使用

建议顺序：

1. 打开相机
2. 执行时间同步
3. 完成相机标定
4. 完成初始标定
5. 开启连续检测

### 已完成标定、仅需再次运行

建议顺序：

1. 启动 `client`
2. 检查设置页参数
3. 打开相机
4. 执行一次时间同步
5. 如环境或相机位置变化明显，再重新执行初始标定
6. 开启连续检测

## 8. 常见问题

### 页面打不开

检查以下内容：

- `client` 是否已经启动
- 访问的 IP 地址是否正确
- `8000` 端口是否可达
- 访问设备与运行 `client` 的机器是否在同一网络，或是否具备可路由路径

### 浏览器打不开摄像头

检查以下内容：

- 是否使用 `HTTPS`
- 浏览器是否授予摄像头权限
- 当前设备是否存在可用摄像头

### 无法开始连续检测

通常表示尚未具备可用的相机标定内参。请先完成相机标定。

### 云端链路不可用

检查以下内容：

- `config/cloud.json` 是否存在且内容正确
- `Transport Mode` 是否与控制端一致
- `session_id` 和 `cloud_host` 是否正确

## 9. 相关文档

- 按钮级说明：`doc/FRONTEND_BUTTON_GUIDE_CN.md`
- 安装说明：`install/INSTALL_CN.md`
- 安装入口说明：`install/README.md`
