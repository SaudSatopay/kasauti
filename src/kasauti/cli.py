"""Kasauti command-line interface.

    kasauti check "Forwarded message text..." [--image URL] [--json]
    kasauti serve [--port 7860]
    kasauti mcp
    kasauti examples
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib import resources
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import Report, VerdictLabel
from .serp import KasautiError, SerpSearcher

console = Console()

_VERDICT_STYLE = {
    VerdictLabel.TRUE: ("bold white on green4", "✔"),
    VerdictLabel.MOSTLY_TRUE: ("bold black on green3", "✔"),
    VerdictLabel.MISLEADING: ("bold black on orange3", "⚠"),
    VerdictLabel.FALSE: ("bold white on red3", "✖"),
    VerdictLabel.OUTDATED: ("bold black on gold3", "⏳"),
    VerdictLabel.UNVERIFIED: ("bold white on grey42", "?"),
    VerdictLabel.SATIRE: ("bold black on plum2", "🎭"),
}


def _confidence_bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled) + f" {value:.0%}"


def _render(report: Report) -> None:
    style, icon = _VERDICT_STYLE[report.overall_label]
    header = Text()
    header.append(f" {icon} {report.overall_label.display.upper()} ", style=style)
    header.append(f"  confidence {_confidence_bar(report.overall_confidence)}")
    console.print()
    console.print(Panel(header, title="[bold]कसौटी KASAUTI[/] · verdict",
                        border_style="yellow"))
    if report.overall_summary:
        console.print(f"  [italic]{report.overall_summary}[/]")
    if report.translation_en:
        console.print(f"  [dim]Translation:[/] {report.translation_en}")

    fp = report.fingerprint
    if fp.signals:
        console.print()
        console.print(f"  [bold]Forward Fingerprint:[/] {fp.score}/100 "
                      f"([{'red' if fp.level == 'high' else 'yellow' if fp.level == 'medium' else 'green'}]{fp.level}[/])")
        for s in fp.signals:
            console.print(f"    • {s.label} — [dim]{s.detail}[/]")

    if report.verdicts:
        console.print()
        table = Table(title="Claims checked", show_lines=True, expand=True)
        table.add_column("Claim", ratio=3)
        table.add_column("Verdict", ratio=1)
        table.add_column("Why", ratio=3)
        claims_by_id = {c.id: c for c in report.claims}
        for v in report.verdicts:
            claim = claims_by_id.get(v.claim_id)
            vstyle, vicon = _VERDICT_STYLE[v.label]
            table.add_row(
                f"[bold]{v.claim_id}[/] {claim.text_en if claim else ''}",
                Text(f"{vicon} {v.label.display}\n{v.confidence:.0%}", style=vstyle.split(' on ')[0]),
                v.rationale or "—",
            )
        console.print(table)

    if report.image is not None:
        console.print()
        console.print(f"  [bold]🖼  Image check (Google Lens):[/] {report.image.note}")

    if report.evidence:
        console.print()
        console.print("  [bold]Evidence[/] (credibility-ranked):")
        for e in report.evidence[:10]:
            date = e.date.date().isoformat() if e.date else (e.date_raw or "")
            console.print(
                f"    [cyan][{e.id}][/] [bold]{e.title[:90]}[/]\n"
                f"         [dim]{e.credibility.label}"
                f"{' · ' + date if date else ''} · {e.link[:90]}[/]"
            )

    if report.suggested_reply:
        console.print()
        console.print(Panel(
            report.suggested_reply,
            title=f"📱 Reply for the group ({report.suggested_reply_lang})",
            border_style="green",
        ))

    console.print()
    mode = "offline fixtures" if report.offline else "live"
    llm = "LLM-assisted" if report.llm_used else "rule-based (no LLM)"
    console.print(
        f"  [dim]{report.searches_used} SerpApi searches ({mode}) · {llm} · "
        f"{report.elapsed_s}s · Kasauti assists your judgement, it does not replace it.[/]"
    )
    console.print()


def _cmd_check(args: argparse.Namespace) -> int:
    from .llm import LLM
    from .pipeline import check

    text = args.text or ""
    if text == "-":
        text = sys.stdin.read()
    if not text.strip() and not args.image:
        console.print("[red]Give me the forward text (or --image URL) to check.[/]")
        return 2

    try:
        searcher = SerpSearcher(offline=True if args.offline else None)
    except KasautiError as exc:
        console.print(f"[red]{exc}[/]")
        return 2

    if args.no_llm:
        import os

        os.environ["KASAUTI_NO_LLM"] = "1"
    llm = LLM()

    def on_event(stage: str, detail: str) -> None:
        if not args.json:
            console.print(f"  [yellow]›[/] [dim]{stage}[/] {detail}")

    if not args.json:
        console.print(Panel(
            (text.strip()[:400] or "(image only)"),
            title="↪ Forwarded many times",
            border_style="grey50",
        ))
    try:
        report = check(
            text,
            image_url=args.image,
            searcher=searcher,
            llm=llm,
            reply_language=args.reply_lang,
            on_event=on_event,
        )
    except KasautiError as exc:
        console.print(f"[red]{exc}[/]")
        return 2

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        _render(report)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import app

    console.print(Panel(
        f"[bold yellow]कसौटी Kasauti[/]\n"
        f"  landing  [bold]http://127.0.0.1:{args.port}/[/]\n"
        f"  checker  [bold]http://127.0.0.1:{args.port}/app[/]\n"
        "[dim]Paste a forward, get a verdict. Ctrl+C to stop.[/]",
        border_style="yellow",
    ))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    try:
        from .mcp_server import run as run_mcp
    except ImportError:
        console.print(
            "[red]MCP support needs the optional dependency:[/] pip install \"kasauti[mcp]\""
        )
        return 2
    run_mcp()
    return 0


def _cmd_examples(_args: argparse.Namespace) -> int:
    console.print("[bold]Bundled example forwards[/] (try: kasauti check \"<paste>\"):\n")
    try:
        root = resources.files("kasauti").joinpath("examples")
        for entry in sorted(root.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(".txt"):
                body = entry.read_text(encoding="utf-8").strip()
                console.print(Panel(body[:500], title=entry.name, border_style="grey50"))
    except (FileNotFoundError, ModuleNotFoundError):
        console.print("[red]No examples bundled in this install.[/]")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="kasauti",
        description="Kasauti (कसौटी) — the touchstone for WhatsApp forwards. "
                    "Check karo, phir forward karo.",
    )
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="Verify a forward (text and/or image URL)")
    p_check.add_argument("text", nargs="?", default="",
                         help="The forwarded message ('-' to read from stdin)")
    p_check.add_argument("--image", help="URL of the attached image (Google Lens check)")
    p_check.add_argument("--json", action="store_true", help="Emit the full report as JSON")
    p_check.add_argument("--offline", action="store_true",
                         help="Use bundled demo fixtures (no API calls, dev only)")
    p_check.add_argument("--no-llm", action="store_true",
                         help="Force rule-based mode even if an LLM key is present")
    p_check.add_argument("--reply-lang", default=None,
                         help="Language for the suggested reply (e.g. hi, en, hi-Latn)")
    p_check.set_defaults(func=_cmd_check)

    p_serve = sub.add_parser("serve", help="Run the Kasauti web app")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=7860)
    p_serve.set_defaults(func=_cmd_serve)

    p_mcp = sub.add_parser("mcp", help="Run as an MCP server (stdio) for AI assistants")
    p_mcp.set_defaults(func=_cmd_mcp)

    p_ex = sub.add_parser("examples", help="Show bundled example forwards")
    p_ex.set_defaults(func=_cmd_examples)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
