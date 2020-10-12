import builtins
import time
from typing import Dict, List, Tuple, TypeVar

import psutil

from . import utils
from .types import Activity, ActivityProcess, Process, SortKey


def update_processes_local(
    processes: Dict[int, Process], new_processes: Dict[int, Process], fs_blocksize: int
) -> Tuple[Tuple[float, float, int, int], List[int], List[ActivityProcess]]:
    """Update resource usage for each process in *local* mode."""
    pids = []
    procs = []
    read_bytes_delta = 0.0
    write_bytes_delta = 0.0
    read_count_delta = 0
    write_count_delta = 0
    for pid, new_proc in new_processes.items():
        try:
            if pid in processes:
                n_io_time = time.time()
                # Getting informations from the previous loop
                proc = processes[pid]
                # Update old process with new informations
                proc.duration = new_proc.duration
                proc.state = new_proc.state
                proc.query = new_proc.query
                proc.appname = new_proc.appname
                proc.client = new_proc.client
                proc.wait = new_proc.wait
                proc.extras.io_wait = new_proc.extras.io_wait
                proc.extras.read_delta = (
                    new_proc.extras.io_counters.read_bytes
                    - proc.extras.io_counters.read_bytes
                ) / (n_io_time - proc.extras.io_time)
                proc.extras.write_delta = (
                    new_proc.extras.io_counters.write_bytes
                    - proc.extras.io_counters.write_bytes
                ) / (n_io_time - proc.extras.io_time)
                proc.extras.io_counters = new_proc.extras.io_counters
                proc.extras.io_time = n_io_time

                # Global io counters
                read_bytes_delta += proc.extras.read_delta
                write_bytes_delta += proc.extras.write_delta
            else:
                # No previous information about this process
                proc = new_proc

            if pid not in pids:
                pids.append(pid)

            if proc.extras.psutil_proc is not None:
                proc.extras.mem_percent = proc.extras.psutil_proc.memory_percent()
                proc.extras.cpu_percent = proc.extras.psutil_proc.cpu_percent(
                    interval=0
                )
            new_processes[pid] = proc
            procs.append(
                ActivityProcess(
                    pid,
                    proc.appname,
                    proc.database,
                    proc.user,
                    proc.client,
                    proc.extras.cpu_percent,
                    proc.extras.mem_percent,
                    proc.extras.read_delta,
                    proc.extras.write_delta,
                    proc.state,
                    proc.query,
                    utils.get_duration(proc.duration),
                    proc.wait,
                    proc.extras.io_wait,
                    proc.extras.is_parallel_worker,
                )
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # store io counters
    if read_bytes_delta > 0:
        read_count_delta += int(read_bytes_delta / fs_blocksize)
    if write_bytes_delta > 0:
        write_count_delta += int(write_bytes_delta / fs_blocksize)

    io_counters = (
        read_bytes_delta,
        write_bytes_delta,
        read_count_delta,
        write_count_delta,
    )

    return io_counters, pids, procs


T = TypeVar("T", Activity, ActivityProcess)


def sorted(activities: List[T], *, key: SortKey, reverse: bool = False) -> List[T]:
    """Return activities sorted.

    >>> activities = [
    ...     ActivityProcess(
    ...         pid="6239",
    ...         appname="pgbench",
    ...         database="pgbench",
    ...         user="postgres",
    ...         client="local",
    ...         cpu=0.1,
    ...         mem=0.993_254_939_413_836,
    ...         read=0.1,
    ...         write=0.282_725_318_098_656_75,
    ...         state="idle in transaction",
    ...         query="UPDATE pgbench_accounts SET abalance = abalance + 141 WHERE aid = 1932841;",
    ...         duration=0,
    ...         wait=False,
    ...         io_wait="N",
    ...         is_parallel_worker=False,
    ...     ),
    ...     ActivityProcess(
    ...         pid="6228",
    ...         appname="pgbench",
    ...         database="pgbench",
    ...         user="postgres",
    ...         client="local",
    ...         cpu=0.2,
    ...         mem=1.024_758_418_061_11,
    ...         read=0.2,
    ...         write=0.113_090_128_201_154_74,
    ...         state="active",
    ...         query="UPDATE pgbench_accounts SET abalance = abalance + 3062 WHERE aid = 7289374;",
    ...         duration=0,
    ...         wait=False,
    ...         io_wait="N",
    ...         is_parallel_worker=True,
    ...     ),
    ... ]

    >>> activities = sorted(activities, key=SortKey.cpu, reverse=True)
    >>> [a.pid for a in activities]
    ['6228', '6239']
    >>> activities = sorted(activities, key=SortKey.mem)
    >>> [a.pid for a in activities]
    ['6239', '6228']
    """
    return builtins.sorted(
        activities,
        key=lambda p: getattr(p, key.name),  # type: ignore  # TODO: avoid getattr()
        reverse=reverse,
    )
