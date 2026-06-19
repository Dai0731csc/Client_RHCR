# Client-RHCR

`Client-RHCR` is the client for our remote hair-cutting robot project. It is used for camera access, calibration, and sending client-side data to the private control system.

## Note

This repository contains only the **client-side code** for the remote hair-cutting robot. The **cloud** and **server/control-side** parts are not public.

Anyone may use this project for academic research. If you are specifically interested in the hair-cutting robot system and would like to discuss further collaboration or request permission to control the remote robot, contact `shuai.li@oulu.fi` or `zhendai.huang@oulu.fi`.

## Deployment

- **Production:** `cloud_tcp` or `cloud_udp` on a machine separate from Cloud and Server. See [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
- **Local dev:** `local_tcp` / `local_udp` (default in repo `config/cloud.json` is often `local_udp` for same-machine debugging).
- Tests and integration scripts: [../testing/README.md](../testing/README.md) only (not under `client/`).

## Documentation

- Install overview: [install/README.md](./install/README.md)
- Installation guide (CN): [install/INSTALL_CN.md](./install/INSTALL_CN.md)
- Installation guide (EN): [install/INSTALL_EN.md](./install/INSTALL_EN.md)
- Usage guide (CN): [docs/USAGE_CN.md](./docs/USAGE_CN.md)
- Usage guide (EN): [docs/USAGE_EN.md](./docs/USAGE_EN.md)
- Frontend button guide (CN): [docs/FRONTEND_BUTTON_GUIDE_CN.md](./docs/FRONTEND_BUTTON_GUIDE_CN.md)
- Frontend button guide (EN): [docs/FRONTEND_BUTTON_GUIDE_EN.md](./docs/FRONTEND_BUTTON_GUIDE_EN.md)
- Raw pose stream protocol: [../docs/RAW_POSE_PROTOCOL.md](../docs/RAW_POSE_PROTOCOL.md)
