"""Envoie un fichier .script au contrôleur (ou URSim) via l'interface secondaire (30002)."""

import argparse
import socket
import time


def send(host: str, port: int, script_path: str) -> None:
    with open(script_path, "rb") as f:
        content = f.read()
    if not content.endswith(b"\n"):
        content += b"\n"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(content)
        print(f"Script envoyé ({len(content)} octets) à {host}:{port}")
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script_path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=30002)
    args = parser.parse_args()
    send(args.host, args.port, args.script_path)
