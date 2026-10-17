"""`scrubgpt-mock-brain`: the fake Brain (plan §4.5; D-025, D-037).

    scrubgpt-mock-brain [--port 8101] [--host 127.0.0.1]

An HTTP server with exactly the endpoints and shapes of the real Brain API (`models/brain_api.py`),
answering deterministically from the fixtures, with no OpenAI key. The app server uses it while
`BRAIN_MODE=mock` (`MOCK_BRAIN_URL`, default `http://localhost:8101`).
"""

import argparse
import sys

DEFAULT_PORT = 8101


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrubgpt-mock-brain",
        description="Start the fake Brain: the Brain API endpoints, answered from the fixtures",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="default: %(default)s")
    parser.add_argument("--host", default="127.0.0.1", help="default: %(default)s")
    args = parser.parse_args(argv)

    import uvicorn

    from scrubgpt_contracts.mock_brain.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
