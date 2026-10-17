"""`scrubgpt-app`: run the app server, or check case packages from the command line.

    scrubgpt-app serve [--host 127.0.0.1] [--port 8000] [--data-dir DIR]
    scrubgpt-app check [--data-dir DIR]                  # every package under DATA_DIR
    scrubgpt-app drop <drop folder> [--reference FILE]   # a Friday drop, file by file (D-038)

Exit codes for `check` and `drop`: 0 = everything loadable, 1 = at least one package is not,
2 = the check could not run (e.g. the folder doesn't exist).
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import replace

from scrubgpt_contracts.validate import ToolError

from scrubgpt_app.catalog import scan
from scrubgpt_app.drop import check_drop, find_reference, render
from scrubgpt_app.settings import Settings, resolve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrubgpt-app", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def data_dir_option(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--data-dir", help="overrides DATA_DIR (relative paths start at the repo root)"
        )

    serve = commands.add_parser("serve", help="run the app server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, help="overrides APP_PORT (default 8000)")
    data_dir_option(serve)

    check = commands.add_parser("check", help="validate every case package under DATA_DIR")
    data_dir_option(check)

    drop = commands.add_parser("drop", help="validate a Friday data drop file by file (D-038)")
    drop.add_argument("folder", help="the drop folder, e.g. <Drive>/drop/2026-10-30")
    drop.add_argument("--reference", help="the Procedure Reference file to check against")
    data_dir_option(drop)
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.load()
    if args.data_dir:
        settings = replace(settings, data_dir=resolve(args.data_dir))
    return settings


def _check(settings: Settings, out: Callable[[str], None]) -> int:
    if not settings.data_dir.is_dir():
        out(f"scrubgpt-app check: DATA_DIR {settings.data_dir} is not a folder")
        return 2
    catalog = scan(settings.data_dir)
    out(f"scrubgpt-app check: {settings.data_dir}")
    for key in sorted(catalog.cases):
        loaded = catalog.cases[key]
        out(
            f"  LOADED   {key}"
            + (f" ({len(loaded.warnings)} warning(s))" if loaded.warnings else "")
        )
        for warning in loaded.warnings:
            out(f"    {warning}")
    for item in [*catalog.rejected, *catalog.rejected_references]:
        out(f"  REJECTED {item.path.name}")
        for problem in item.problems:
            out(f"    {problem}")
    for procedure_id in sorted(catalog.references):
        out(f"  REFERENCE {procedure_id}")
    out(f"{len(catalog.cases)} loaded, {len(catalog.rejected)} rejected")
    return 1 if catalog.rejected or catalog.rejected_references else 0


def _drop(args: argparse.Namespace, settings: Settings, out: Callable[[str], None]) -> int:
    folder = resolve(args.folder)
    reference = resolve(args.reference) if args.reference else None
    try:
        results = check_drop(folder, reference or find_reference(folder, settings.data_dir))
    except ToolError as exc:
        out(f"scrubgpt-app drop: {exc}")
        return 2
    out(render(folder, results))
    if any(package.not_run for package in results):
        return 2
    return 0 if results and all(package.loadable for package in results) else 1


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    # Windows consoles may not encode every character of a Japanese path or message.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    args = _parser().parse_args(argv)
    settings = _settings(args)
    if args.command == "check":
        return _check(settings, out)
    if args.command == "drop":
        return _drop(args, settings, out)
    import uvicorn

    from scrubgpt_app.api import create_app

    port = args.port or settings.port
    out(f"scrubgpt-app: DATA_DIR {settings.data_dir}, http://{args.host}:{port}")
    uvicorn.run(create_app(settings), host=args.host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
