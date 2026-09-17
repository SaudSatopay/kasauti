"""Kasauti as an MCP server — plug fact-checking into any AI assistant.

Run:  kasauti mcp        (stdio transport)

Claude Desktop config example:
{
  "mcpServers": {
    "kasauti": {
      "command": "kasauti",
      "args": ["mcp"],
      "env": { "SERPAPI_API_KEY": "..." }
    }
  }
}
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "kasauti",
    instructions=(
        "Kasauti verifies viral claims and WhatsApp forwards against live web "
        "evidence (Google Search, Google News, Indian fact-check desks and Google "
        "Lens, via SerpApi). Use verify_forward for any 'is this real?' question "
        "about news, schemes, health claims or viral images."
    ),
)


@mcp.tool()
def verify_forward(text: str, image_url: Optional[str] = None) -> str:
    """Fact-check a forwarded message or viral claim against live search evidence.

    Args:
        text: The forwarded message / claim (Hindi, Hinglish or English).
        image_url: Optional URL of an attached image for reverse-image analysis.

    Returns a JSON report: overall verdict, per-claim verdicts with confidence,
    credibility-ranked evidence with links, and a suggested polite correction.
    """
    from .pipeline import check

    report = check(text, image_url=image_url)
    compact = {
        "overall_verdict": report.overall_label.value,
        "confidence": report.overall_confidence,
        "summary": report.overall_summary,
        "forward_fingerprint": {
            "score": report.fingerprint.score,
            "level": report.fingerprint.level,
            "signals": [s.label for s in report.fingerprint.signals],
        },
        "claims": [
            {
                "claim": next((c.text_en for c in report.claims if c.id == v.claim_id), ""),
                "verdict": v.label.value,
                "confidence": v.confidence,
                "rationale": v.rationale,
                "citations": [
                    {"title": e.title, "url": e.link, "source_type": e.credibility.label}
                    for e in (report.evidence_by_id(cid) for cid in v.citation_ids)
                    if e is not None
                ],
            }
            for v in report.verdicts
        ],
        "image_analysis": report.image.note if report.image else None,
        "suggested_reply": report.suggested_reply,
        "serpapi_searches_used": report.searches_used,
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
