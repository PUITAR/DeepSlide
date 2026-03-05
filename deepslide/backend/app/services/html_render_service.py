import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import anyio


@dataclass
class HtmlRenderOptions:
    dpr: int = 2
    timeout_ms: int = 60000
    rewrite_project_id_assets: bool = True


def _is_uuid(s: str) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            str(s or ""),
        )
    )


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _safe_int_from_filename(fn: str) -> int:
    m = re.search(r"(\d+)", str(fn or ""))
    return int(m.group(1)) if m else 10**9


def _cache_png_path(cache_dir: str, html_filename: str, dpr: int, rewrite_assets: bool) -> str:
    base = os.path.basename(str(html_filename or "slide.html"))
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base).strip("._") or "slide.html"
    stem, _ = os.path.splitext(base)
    rw = "rw1" if rewrite_assets else "rw0"
    return os.path.join(cache_dir, f"{stem}.dpr{int(dpr)}.{rw}.png")


def _should_reuse(cache_png: str, html_path: str) -> bool:
    try:
        if not os.path.exists(cache_png) or not os.path.isfile(cache_png):
            return False
        if not os.path.exists(html_path) or not os.path.isfile(html_path):
            return False
        return os.path.getmtime(cache_png) >= os.path.getmtime(html_path)
    except Exception:
        return False


def _rewrite_asset_url(url: str, target_project_id: str) -> Optional[str]:
    try:
        u = urllib.parse.urlsplit(url)
        m = re.match(r"^/api/v1/projects/([^/]+)/asset$", u.path)
        if not m:
            return None
        old_pid = m.group(1)
        if not _is_uuid(old_pid) or old_pid == target_project_id:
            return None
        new_path = f"/api/v1/projects/{target_project_id}/asset"
        return urllib.parse.urlunsplit((u.scheme, u.netloc, new_path, u.query, u.fragment))
    except Exception:
        return None


def render_html_slide_to_png(
    *,
    html_url: str,
    html_path: str,
    project_id: str,
    cache_dir: str,
    html_filename: str,
    options: HtmlRenderOptions,
) -> Dict[str, Any]:
    dpr = int(options.dpr or 2)
    if dpr < 1:
        dpr = 1
    if dpr > 4:
        dpr = 4

    timeout_ms = int(options.timeout_ms or 600000)
    if timeout_ms < 50000:
        timeout_ms = 50000

    rewrite_assets = bool(options.rewrite_project_id_assets)

    out_png = _cache_png_path(cache_dir, html_filename, dpr=dpr, rewrite_assets=rewrite_assets)
    _ensure_dir(os.path.dirname(out_png))

    if _should_reuse(out_png, html_path):
        return {"success": True, "png_path": out_png, "cached": True, "meta": {}}

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        return {
            "success": False,
            "error": f"Playwright not available: {type(e).__name__}: {str(e)}",
            "hint": "pip install playwright && playwright install chromium",
        }

    t0 = time.time()
    meta: Dict[str, Any] = {"html_url": html_url, "dpr": dpr, "timeout_ms": timeout_ms}
    console_errors: List[str] = []
    network_errors: List[Dict[str, Any]] = []
    page_errors: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=float(dpr))
            page = context.new_page()

            def _on_console(msg):
                try:
                    if msg.type() == "error":
                        console_errors.append(str(msg.text() or "")[:400])
                except Exception:
                    pass

            def _on_page_error(exc):
                try:
                    page_errors.append(str(exc)[:400])
                except Exception:
                    pass

            def _on_request_finished(req):
                try:
                    resp = req.response()
                except Exception:
                    resp = None
                if not resp:
                    return
                try:
                    status = int(resp.status)
                except Exception:
                    status = -1
                if status >= 400:
                    network_errors.append(
                        {"url": req.url, "status": status, "method": req.method, "resource_type": req.resource_type}
                    )

            def _on_request_failed(req):
                try:
                    network_errors.append(
                        {
                            "url": req.url,
                            "status": -1,
                            "method": req.method,
                            "resource_type": req.resource_type,
                            "failed": True,
                            "failure": getattr(req, "failure", None),
                        }
                    )
                except Exception:
                    pass

            page.on("console", _on_console)
            page.on("pageerror", _on_page_error)
            page.on("requestfinished", _on_request_finished)
            page.on("requestfailed", _on_request_failed)

            page.add_init_script(
                """
                (() => {
                  try { document.documentElement.classList.add('motion-static'); } catch (e) {}
                  try { document.documentElement.dataset.mode = 'preview'; } catch (e) {}
                  try { document.body && (document.body.dataset.mode = 'preview'); } catch (e) {}
                  try { document.body && document.body.classList.add('motion-static'); } catch (e) {}
                })();
                """
            )
            page.add_style_tag(
                content="""
                html, body { margin: 0 !important; padding: 0 !important; overflow: hidden !important; }
                .stage { padding: 0 !important; margin: 0 !important; }
                .slide { height: var(--page-h, 900px) !important; min-height: var(--page-h, 900px) !important; overflow: hidden !important; }
                """
            )

            if rewrite_assets:
                def _route_handler(route, request):
                    new_url = _rewrite_asset_url(request.url, target_project_id=project_id)
                    if new_url:
                        return route.continue_(url=new_url)
                    return route.continue_()

                page.route("**/api/v1/projects/*/asset**", _route_handler)

            page.goto(html_url, wait_until="domcontentloaded", timeout=timeout_ms)

            try:
                page.evaluate("() => (document.fonts ? document.fonts.ready : Promise.resolve(true))")
            except Exception:
                pass

            page.wait_for_timeout(250)

            js_ready = r"""
            () => {
              function allImagesReady() {
                const imgs = Array.from(document.images || []);
                if (!imgs.length) return true;
                return imgs.every(im => {
                  if (!im) return true;
                  const srcAttr = (im.getAttribute('src') || '').trim();
                  if (!srcAttr) return true;
                  if (!im.complete) return false;
                  const nw = (im.naturalWidth || 0);
                  if (nw > 0) return true;
                  const cs = window.getComputedStyle(im);
                  const hidden = (cs && (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0'));
                  if (hidden) return true;
                  const rects = (typeof im.getClientRects === 'function') ? im.getClientRects() : [];
                  if (!rects || rects.length === 0) return true;
                  return false;
                });
              }
              const slide = document.querySelector('.slide');
              const hasEchart = !!document.querySelector('.echart');
              const echartHasCanvas = !!document.querySelector('.echart canvas');
              const echartReady = !!document.querySelector('.echart[data-echarts-ready="1"]');
              const echartHasSvg = !!document.querySelector('.echart svg');
              const hasDiagram = !!document.querySelector('.diagram-svg svg');
              return {
                has_slide: !!slide,
                images_ready: allImagesReady(),
                has_echart: hasEchart,
                echart_canvas: echartHasCanvas,
                echart_ready: echartReady,
                echart_svg: echartHasSvg,
                has_diagram_svg: hasDiagram
              };
            }
            """
            wait_start = time.time()
            last: Dict[str, Any] = {}
            while (time.time() - wait_start) * 1000 < min(15000, timeout_ms):
                try:
                    cur = page.evaluate(js_ready)
                    if isinstance(cur, dict):
                        last = cur
                    else:
                        cur = {}
                except Exception:
                    cur = {}
                need_echart = bool(cur.get("has_echart"))
                need_diagram = bool(cur.get("has_diagram_svg"))
                ok = bool(cur.get("has_slide")) and bool(cur.get("images_ready"))
                if need_echart:
                    ok = ok and (bool(cur.get("echart_ready")) or bool(cur.get("echart_canvas")) or bool(cur.get("echart_svg")))
                if need_diagram:
                    ok = ok and bool(cur.get("has_diagram_svg"))
                if ok:
                    break
                page.wait_for_timeout(250)

            meta["ready"] = last

            loc = page.locator(".slide")
            if loc.count() > 0:
                loc.first.screenshot(path=out_png)
            else:
                page.screenshot(path=out_png, full_page=False)

        finally:
            try:
                browser.close()
            except Exception:
                pass

    meta["timing_ms"] = int((time.time() - t0) * 1000)
    meta["console_error_count"] = len(console_errors)
    meta["network_error_count"] = len(network_errors)
    meta["page_error_count"] = len(page_errors)
    meta["console_errors"] = console_errors[:20]
    meta["network_errors"] = network_errors[:50]
    meta["page_errors"] = page_errors[:20]

    if not os.path.exists(out_png):
        return {"success": False, "error": "screenshot not created", "meta": meta}

    return {"success": True, "png_path": out_png, "cached": False, "meta": meta}


_PLAYWRIGHT_LIMITER = anyio.CapacityLimiter(1)


async def render_html_slide_to_png_async(
    *,
    html_url: str,
    html_path: str,
    project_id: str,
    cache_dir: str,
    html_filename: str,
    options: HtmlRenderOptions,
) -> Dict[str, Any]:
    return await anyio.to_thread.run_sync(
        lambda: render_html_slide_to_png(
            html_url=html_url,
            html_path=html_path,
            project_id=project_id,
            cache_dir=cache_dir,
            html_filename=html_filename,
            options=options,
        ),
        limiter=_PLAYWRIGHT_LIMITER,
    )
