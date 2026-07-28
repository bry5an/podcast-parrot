import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="kotoba-backend")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--auth-token", default=None)
    args = parser.parse_args()

    # Must happen before importing app.main: app.db resolves its writable
    # paths from KOTOBA_DATA_DIR at import time.
    if args.data_dir:
        os.environ["KOTOBA_DATA_DIR"] = args.data_dir
    if args.auth_token:
        os.environ["KOTOBA_AUTH_TOKEN"] = args.auth_token

    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
