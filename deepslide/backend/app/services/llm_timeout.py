import concurrent.futures
from typing import Any, Callable, Optional


def run_with_timeout(fn: Callable[[], Any], timeout_seconds: float, fallback: Any = None) -> Any:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            return fut.result(timeout=float(timeout_seconds))
    except concurrent.futures.TimeoutError:
        return fallback
    except Exception:
        return fallback


def safe_agent_step(agent: Any, message: Any, timeout_seconds: float) -> Optional[Any]:
    def _call():
        return agent.step(message)

    return run_with_timeout(_call, timeout_seconds=timeout_seconds, fallback=None)

