import multiprocessing
import os
from collections.abc import Iterable
from typing import Any

# A small helper to run selector._passes_filters in parallel across codes.
# Each worker process receives the selector object via initializer (pickled),
# then processes a list of (code, hist) tuples and returns the codes that pass.

_GLOBAL_SELECTOR = None


def _init_worker(selector: Any) -> None:
    global _GLOBAL_SELECTOR
    _GLOBAL_SELECTOR = selector


def _worker_task(item: tuple[str, Any]) -> str | None:
    global _GLOBAL_SELECTOR
    code, hist = item
    try:
        if _GLOBAL_SELECTOR is None:
            print("_GLOBAL_SELECTOR is not set")
            return None
        ok = _GLOBAL_SELECTOR._passes_filters(hist)
        return code if ok else None
    except Exception:
        return None


def parallel_select_helper(
    selector: Any,
    task_list: Iterable[tuple[str, Any]],
    processes: int | None = None,
    chunksize: int = 1,
) -> list[str]:
    """Run selector._passes_filters(hist) in parallel for given (code, hist) tasks.

    - selector: object that exposes `_passes_filters(hist)`
    - task_list: iterable of (code, hist DataFrame) tuples
    - processes: number of worker processes (defaults to cpu_count())
    Returns list of codes that passed.
    """
    items_list = list(task_list)
    if not items_list:
        return []

    procs = int(processes) if processes else (os.cpu_count() or 2)

    try:
        with multiprocessing.Pool(
            processes=procs, initializer=_init_worker, initargs=(selector,)
        ) as pool:
            results = pool.map(_worker_task, items_list, chunksize)
    except Exception:
        # Fallback to sequential if multiprocessing fails for any reason
        results = []
        _init_worker(selector)
        for it in items_list:
            results.append(_worker_task(it))

    return [r for r in results if r]
