import argparse
from pathlib import Path
import sys


def _ensure_gripperapp_on_sys_path():
    gripperapp_dir = Path(__file__).resolve().parents[1]
    if str(gripperapp_dir) not in sys.path:
        sys.path.insert(0, str(gripperapp_dir))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ngrok",
        action="store_true",
        help="Start ngrok alongside the HTTPS + WSS server",
    )
    parser.add_argument(
        "--ngrok-api-port",
        type=int,
        default=4040,
        help="Local ngrok API port used to print the public URL",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    from aiohttp import web

    from backend import HOST, PORT, create_app, create_ssl_context

    _ensure_gripperapp_on_sys_path()
    from ngrok_utils import start_ngrok, wait_for_ngrok_public_url

    if args.ngrok:
        ngrok_process = start_ngrok(PORT)
        public_url, ngrok_exit_code = wait_for_ngrok_public_url(
            ngrok_process, api_port=args.ngrok_api_port
        )
        print(f"ngrok starting for https://localhost:{PORT}")
        if public_url:
            print(f"Public URL: {public_url}")
            print(f"App URL: {public_url}/")
        elif ngrok_exit_code is not None:
            raise RuntimeError(
                "ngrok exited before a public URL became available.\n"
                "Most common cause: invalid or missing authtoken (ERR_NGROK_105).\n"
                "Fix: run `ngrok config add-authtoken <YOUR_TOKEN>` then retry."
            )
        else:
            print("ngrok started, but public URL is not available yet from the local API")

    print(f"HTTPS + WSS server running at https://{HOST}:{PORT}")
    web.run_app(create_app(), host=HOST, port=PORT, ssl_context=create_ssl_context())
