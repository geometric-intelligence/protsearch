#!/usr/bin/env python3
"""
Deploy the Flask backend (backend/Dockerfile) to Cloud Run.

Requires: gcloud CLI, authenticated user, billing OPEN on the target project.

Usage:
  python scripts/deploy_backend_cloud_run.py --project protsearch
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys


def read_google_api_key(env_path: pathlib.Path) -> str:
    if not env_path.is_file():
        raise SystemExit(f"Env file not found: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("GOOGLE_API_KEY="):
            return s.split("=", 1)[1].strip()
    raise SystemExit(f"No uncommented GOOGLE_API_KEY= in {env_path}")


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def find_gcloud() -> str:
    gcloud = shutil.which("gcloud")
    if gcloud:
        return gcloud
    candidates = [
        pathlib.Path.home() / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd",
        pathlib.Path("/usr/local/bin/gcloud"),
        pathlib.Path("/opt/homebrew/bin/gcloud"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    raise SystemExit("gcloud not found in PATH or common install locations")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    backend = root / "backend"
    p = argparse.ArgumentParser(description="Deploy backend to Cloud Run from Dockerfile")
    p.add_argument("--project", default="protsearch", help="GCP project id")
    p.add_argument("--service", default="protsearch-backend", help="Cloud Run service name")
    p.add_argument("--region", default="us-central1", help="Region")
    p.add_argument(
        "--env-file",
        type=pathlib.Path,
        default=root / ".env",
        help="Path to .env containing GOOGLE_API_KEY",
    )
    args = p.parse_args()

    gcloud = find_gcloud()

    key = read_google_api_key(args.env_file)
    if not key:
        raise SystemExit("GOOGLE_API_KEY is empty")

    gemini_primary = "gemini-2.5-pro"
    gemini_fallback = "gemini-2.5-flash"
    env_vars = (
        f"GOOGLE_API_KEY={key},"
        f"GEMINI_SUMMARY_MODEL={gemini_primary},"
        f"GEMINI_SUMMARY_FALLBACK_MODEL={gemini_fallback}"
    )

    run([gcloud, "config", "set", "project", args.project])
    run(
        [
            gcloud,
            "services",
            "enable",
            "run.googleapis.com",
            "cloudbuild.googleapis.com",
            "artifactregistry.googleapis.com",
            "--project",
            args.project,
        ]
    )
    run(
        [
            gcloud,
            "run",
            "deploy",
            args.service,
            "--source",
            str(backend),
            "--region",
            args.region,
            "--project",
            args.project,
            "--allow-unauthenticated",
            "--set-env-vars",
            env_vars,
        ]
    )
    print("Done. Point your frontend at the printed Service URL.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
