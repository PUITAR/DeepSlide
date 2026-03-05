import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SandboxIssue(BaseModel):
    type: str = Field(..., description="JS_ERROR|NETWORK_ERROR|OVERFLOW|MISSING_ELEMENT|OTHER")
    severity: str = Field(..., description="low|medium|high|critical")
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class SandboxReport(BaseModel):
    issues: List[SandboxIssue] = Field(default_factory=list)
    layout_snapshot: Dict[str, Any] = Field(default_factory=dict)
    console_logs: List[str] = Field(default_factory=list)
    network_logs: List[Dict[str, Any]] = Field(default_factory=list)


def run_sandbox(url: str, timeout_ms: int = 8000) -> SandboxReport:
    """Run a very lightweight headless-browser sandbox against a single slide HTML.

    Implementation notes:
    - Uses Playwright if available; otherwise returns an empty report.
    - Intended to be best-effort: failures should never crash the caller.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return SandboxReport()

    issues: List[SandboxIssue] = []
    console_logs: List[str] = []
    network_logs: List[Dict[str, Any]] = []
    layout_snapshot: Dict[str, Any] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()

                # Console / JS errors
                def _on_console(msg):
                    text = msg.text()
                    console_logs.append(text)
                    if msg.type() == "error":
                        issues.append(
                            SandboxIssue(
                                type="JS_ERROR",
                                severity="high",
                                message=text[:300],
                                details={"location": msg.location},
                            )
                        )

                page.on("console", _on_console)

                def _on_page_error(exc):
                    text = str(exc)
                    console_logs.append(f"[pageerror] {text}")
                    issues.append(
                        SandboxIssue(
                            type="JS_ERROR",
                            severity="high",
                            message=text[:300],
                            details={},
                        )
                    )

                page.on("pageerror", _on_page_error)

                def _on_request_finished(request):
                    try:
                        response = request.response()
                    except Exception:
                        response = None
                    if not response:
                        return
                    status = response.status
                    entry = {
                        "url": request.url,
                        "status": status,
                        "method": request.method,
                        "resource_type": request.resource_type,
                    }
                    network_logs.append(entry)
                    if status >= 400:
                        issues.append(
                            SandboxIssue(
                                type="NETWORK_ERROR",
                                severity="medium" if status < 500 else "high",
                                message=f"{status} for {request.url}",
                                details=entry,
                            )
                        )

                page.on("requestfinished", _on_request_finished)

                page.goto(url, wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(min(timeout_ms, 2000))

                # Basic layout snapshot: viewport and key elements
                js = """
                () => {
                  const vp = { width: window.innerWidth, height: window.innerHeight };
                  function rect(sel) {
                    const el = document.querySelector(sel);
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return { x: r.x, y: r.y, width: r.width, height: r.height };
                  }
                  return {
                    viewport: vp,
                    slide_body: rect('.slide-body'),
                    hero_img: rect('.hero-img'),
                    roi_grid: rect('.roi-grid'),
                    roi_tile: rect('.roi-tile'),
                    roi_tiles_count: document.querySelectorAll('.roi-tile').length,
                    diagram_root: rect('[data-diagram-root], .diagram-root'),
                    has_vertical_scroll: document.documentElement.scrollHeight > window.innerHeight + 4
                  };
                }
                """
                layout_snapshot = page.evaluate(js)

                # Simple overflow check
                if layout_snapshot and layout_snapshot.get("has_vertical_scroll"):
                    issues.append(
                        SandboxIssue(
                            type="OVERFLOW",
                            severity="medium",
                            message="Page has vertical overflow beyond viewport.",
                            details={},
                        )
                    )
            finally:
                browser.close()
    except Exception:
        # Best-effort; swallow sandbox-level failures
        return SandboxReport()

    return SandboxReport(
        issues=issues,
        layout_snapshot=layout_snapshot or {},
        console_logs=console_logs,
        network_logs=network_logs,
    )
