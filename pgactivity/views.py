import enum
import functools
import itertools
from datetime import timedelta
from textwrap import dedent
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    NoReturn,
    Optional,
    Tuple,
    Union,
)

import humanize
from blessed import Terminal
from blessed.formatters import FormattingString

from .keys import (
    BINDINGS,
    EXIT_KEY,
    HELP as HELP_KEY,
    KEYS_BY_QUERYMODE,
    Key,
    MODES,
    PAUSE_KEY,
)
from .types import (
    BWProcess,
    ActivityStats,
    ColumnTitle,
    DBInfo,
    Flag,
    Host,
    IOCounter,
    LocalRunningProcess,
    MemoryInfo,
    QueryDisplayMode,
    QueryMode,
    RunningProcess,
    SortKey,
    SystemInfo,
    UI,
)
from . import utils
from .activities import sorted as sorted_processes

LINE_COLORS = {
    "pid": {"default": "cyan", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "database": {
        "default": "black_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "appname": {
        "default": "black_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "user": {
        "default": "black_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "client": {"default": "cyan", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "cpu": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "mem": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "read": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "write": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "time_red": {"default": "red", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "time_yellow": {
        "default": "yellow",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "time_green": {
        "default": "green",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "wait_green": {
        "default": "green_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "wait_red": {
        "default": "red_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "state_default": {
        "default": "normal",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "state_yellow": {
        "default": "yellow",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "state_green": {
        "default": "green",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "state_red": {"default": "red", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "query": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "relation": {"default": "cyan", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "type": {"default": "normal", "cursor": "cyan_reverse", "yellow": "yellow_bold"},
    "mode_yellow": {
        "default": "yellow_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
    "mode_red": {
        "default": "red_bold",
        "cursor": "cyan_reverse",
        "yellow": "yellow_bold",
    },
}


line_counter = functools.partial(itertools.count, step=-1)
naturalsize = functools.partial(humanize.naturalsize, gnu=True, format="%.2f")


def limit(func: Callable[..., Iterable[str]]) -> Callable[..., int]:
    """View decorator handling screen height limit.

    >>> term = Terminal()

    >>> def view(term, n, *, prefix="line"):
    ...     for i in range(n):
    ...         yield f"{prefix} #{i}"

    >>> count = line_counter(2)
    >>> limit(view)(term, 3, lines_counter=count)
    line #0
    line #1
    >>> count
    count(0, -1)
    >>> count = line_counter(3)
    >>> limit(view)(term, 2, lines_counter=count)
    line #0
    line #1
    >>> count
    count(1, -1)
    >>> limit(view)(term, 3, prefix="row")
    row #0
    row #1
    row #2

    A single line is displayed with an EOL as well:
    >>> count = line_counter(10)
    >>> limit(view)(term, 1, lines_counter=count) or print("<--", end="")
    line #0
    <--
    >>> count
    count(9, -1)
    """

    @functools.wraps(func)
    def wrapper(term: Terminal, *args: Any, **kwargs: Any) -> None:
        counter = kwargs.pop("lines_counter", None)
        for line in func(term, *args, **kwargs):
            print(line)
            if counter is not None and next(counter) == 1:
                break

    return wrapper


@functools.singledispatch
def render(x: NoReturn, column_width: int) -> str:
    raise AssertionError(f"not implemented for type '{type(x).__name__}'")


@render.register(MemoryInfo)
def render_meminfo(m: MemoryInfo, column_width: int) -> str:
    used, total = naturalsize(m.used), naturalsize(m.total)
    return _columns(f"{m.percent}%", f"{used}/{total}", column_width)


@render.register(IOCounter)
def render_iocounter(i: IOCounter, column_width: int) -> str:
    hbytes = naturalsize(i.bytes)
    return _columns(f"{hbytes}/s", f"{i.count}/s", column_width)


def _columns(left: str, right: str, total_width: int) -> str:
    column_width, r = divmod(total_width, 2)
    if r:
        column_width -= 1
    return " - ".join([left.rjust(column_width - 1), right.ljust(column_width - 1)])


@limit
def help(term: Terminal, version: str, is_local: bool) -> Iterable[str]:
    """Render help menu."""
    project_url = "https://github.com/dalibo/pg_activity"
    intro = dedent(
        f"""\
    {term.bold_green}pg_activity {version} - {term.link(project_url, project_url)}
    {term.normal}Released under PostgreSQL License.
    """
    )

    def key_mappings(keys: Iterable[Key]) -> Iterable[str]:
        for key in keys:
            key_name = key.name or key.value
            yield f"{term.bright_cyan}{key_name.rjust(10)}{term.normal}: {key.description}"

    footer = "Press any key to exit."
    for line in intro.splitlines():
        yield line
    yield ""

    bindings = BINDINGS
    if not is_local:
        bindings = [b for b in bindings if not b.local_only]
    yield from key_mappings(bindings)
    yield "Mode"
    yield from key_mappings(MODES)
    yield ""
    yield footer


@limit
def header(
    term: Terminal,
    ui: UI,
    *,
    host: Host,
    dbinfo: DBInfo,
    tps: int,
    active_connections: int,
    system_info: Optional[SystemInfo] = None,
) -> Iterator[str]:
    """Return window header lines."""
    pg_host = f"{host.user}@{host.host}:{host.port}/{host.dbname}"
    yield (
        " - ".join(
            [
                host.pg_version,
                f"{term.bold}{host.hostname}{term.normal}",
                f"{term.cyan}{pg_host}{term.normal}",
                f"Ref.: {ui.refresh_time}s",
            ]
            + ([f"Min. duration: {ui.min_duration}s"] if ui.min_duration else [])
        )
    )

    def row(*columns: Tuple[str, str, int]) -> str:
        return " | ".join(
            f"{title}: {value.center(width)}" for title, value, width in columns
        ).rstrip()

    def indent(text: str, indent: int = 1) -> str:
        return " " * indent + text

    col_width = 30  # TODO: use screen size

    total_size = naturalsize(dbinfo.total_size)
    size_ev = naturalsize(dbinfo.size_ev)
    yield indent(
        row(
            (
                "Size",
                _columns(total_size, f"{size_ev}/s", 20),
                col_width,
            ),
            ("TPS", f"{term.bold_green}{str(tps).rjust(11)}{term.normal}", 20),
            (
                "Active connections",
                f"{term.bold_green}{str(active_connections).rjust(11)}{term.normal}",
                20,
            ),
            (
                "Duration mode",
                f"{term.bold_green}{ui.duration_mode.name.rjust(11)}{term.normal}",
                5,
            ),
        )
    )

    if system_info is not None:
        yield indent(
            row(
                ("Mem.", render(system_info.memory, col_width // 2), col_width),
                ("IO Max", f"{system_info.max_iops:8}/s", col_width // 4),
            )
        )
        yield indent(
            row(
                ("Swap", render(system_info.swap, col_width // 2), col_width),
                (
                    "Read",
                    render(system_info.io_read, col_width // 2 - len("Read")),
                    col_width,
                ),
            )
        )
        load = system_info.load
        yield indent(
            row(
                (
                    "Load",
                    f"{load.avg1:.2f} {load.avg5:.2f} {load.avg15:.2f}",
                    col_width,
                ),
                (
                    "Write",
                    render(system_info.io_write, col_width // 2 - len("Write")),
                    col_width,
                ),
            )
        )


@limit
def query_mode(term: Terminal, ui: UI) -> Iterator[str]:
    r"""Display query mode title.

    >>> from pgactivity.types import QueryMode, UI

    >>> term = Terminal()
    >>> ui = UI(query_mode=QueryMode.blocking)
    >>> query_mode(term, ui)
                                    BLOCKING QUERIES
    >>> ui = UI(query_mode=QueryMode.activities, in_pause=True)
    >>> query_mode(term, ui)  # doctest: +NORMALIZE_WHITESPACE
                                    PAUSE
    """
    if ui.in_pause:
        yield term.black_bold_on_orange(term.center("PAUSE", fillchar=" "))
    else:
        yield term.green_bold(
            term.center(ui.query_mode.value.upper(), fillchar=" ").rstrip()
        )


@enum.unique
class Column(enum.Enum):
    """Model for each column that may appear in the table."""

    appname = ColumnTitle(
        name="APP",
        template_h="%16s ",
        flag=Flag.APPNAME,
        mandatory=False,
        sort_key=None,
    )
    client = ColumnTitle(
        name="CLIENT",
        template_h="%16s ",
        flag=Flag.CLIENT,
        mandatory=False,
        sort_key=None,
    )
    cpu = ColumnTitle(
        name="CPU%",
        template_h="%6s ",
        flag=Flag.CPU,
        mandatory=False,
        sort_key=SortKey.cpu,
    )
    database = ColumnTitle(
        name="DATABASE",
        template_h="%-16s ",
        flag=Flag.DATABASE,
        mandatory=False,
        sort_key=None,
    )
    iowait = ColumnTitle(
        name="IOW", template_h="%4s ", flag=Flag.IOWAIT, mandatory=False, sort_key=None
    )
    mem = ColumnTitle(
        name="MEM%",
        template_h="%4s ",
        flag=Flag.MEM,
        mandatory=False,
        sort_key=SortKey.mem,
    )
    mode = ColumnTitle(
        name="MODE", template_h="%16s ", flag=Flag.MODE, mandatory=False, sort_key=None
    )
    pid = ColumnTitle(
        name="PID", template_h="%-6s ", flag=Flag.PID, mandatory=False, sort_key=None
    )
    query = ColumnTitle(
        name="Query", template_h=" %2s", flag=None, mandatory=True, sort_key=None
    )
    read = ColumnTitle(
        name="READ/s",
        template_h="%8s ",
        flag=Flag.READ,
        mandatory=False,
        sort_key=SortKey.read,
    )
    relation = ColumnTitle(
        name="RELATION",
        template_h="%9s ",
        flag=Flag.RELATION,
        mandatory=False,
        sort_key=None,
    )
    state = ColumnTitle(
        name="state", template_h=" %17s  ", flag=None, mandatory=True, sort_key=None
    )
    time = ColumnTitle(
        name="TIME+",
        template_h="%9s ",
        flag=Flag.TIME,
        mandatory=False,
        sort_key=SortKey.duration,
    )
    type = ColumnTitle(
        name="TYPE", template_h="%16s ", flag=Flag.TYPE, mandatory=False, sort_key=None
    )
    user = ColumnTitle(
        name="USER", template_h="%16s ", flag=Flag.USER, mandatory=False, sort_key=None
    )
    wait = ColumnTitle(
        name="W", template_h="%2s ", flag=Flag.WAIT, mandatory=False, sort_key=None
    )
    write = ColumnTitle(
        name="WRITE/s",
        template_h="%8s ",
        flag=Flag.WRITE,
        mandatory=False,
        sort_key=SortKey.write,
    )


COLUMNS_BY_QUERYMODE: Dict[QueryMode, List[Column]] = {
    QueryMode.activities: [
        Column.pid,
        Column.database,
        Column.appname,
        Column.user,
        Column.client,
        Column.cpu,
        Column.mem,
        Column.read,
        Column.write,
        Column.time,
        Column.wait,
        Column.iowait,
        Column.state,
        Column.query,
    ],
    QueryMode.waiting: [
        Column.pid,
        Column.database,
        Column.appname,
        Column.user,
        Column.client,
        Column.relation,
        Column.type,
        Column.mode,
        Column.time,
        Column.state,
        Column.query,
    ],
    QueryMode.blocking: [
        Column.pid,
        Column.database,
        Column.appname,
        Column.user,
        Column.client,
        Column.relation,
        Column.type,
        Column.mode,
        Column.time,
        Column.state,
        Column.query,
    ],
}


@limit
def columns_header(term: Terminal, ui: UI) -> Iterator[str]:
    """Yield columns header lines."""
    columns = (c.value for c in COLUMNS_BY_QUERYMODE[ui.query_mode])
    htitles = []
    for column in columns:
        if column.mandatory or (column.flag & ui.flag):
            color = getattr(term, f"black_on_{column.color(ui.sort_key)}")
            htitles.append(f"{color}{column.render()}")
    yield term.ljust("".join(htitles), fillchar=" ") + term.normal


def get_indent(mode: QueryMode, flag: Flag) -> str:
    """Return identation for Query column.

    >>> get_indent(QueryMode.activities, Flag.CPU)
    '                           '
    >>> flag = Flag.PID | Flag.DATABASE | Flag.APPNAME | Flag.RELATION
    >>> get_indent(QueryMode.activities, flag)
    '                                                             '
    """
    indent = ""
    columns = (c.value for c in COLUMNS_BY_QUERYMODE[mode])
    for idx, column in enumerate(columns):
        if column.mandatory or column.flag & flag:
            if column.name != "Query":
                indent += column.template_h % " "
    return indent


def format_query(query: str, is_parallel_worker: bool) -> str:
    r"""Return the query string formatted.

    >>> print(format_query("SELECT 1", True))
    \_ SELECT 1
    >>> format_query("SELECT   1", False)
    'SELECT 1'
    """
    prefix = r"\_ " if is_parallel_worker else ""
    return prefix + utils.clean_str(query)


def format_duration(duration: Optional[float]) -> Tuple[str, str]:
    """Return a string from 'duration' value along with the color for rendering.

    >>> format_duration(None)
    ('N/A     ', 'time_green')
    >>> format_duration(-0.000062)
    ('0.000000', 'time_green')
    >>> format_duration(0.1)
    ('0.100000', 'time_green')
    >>> format_duration(1.2)
    ('00:01.20', 'time_yellow')
    >>> format_duration(12345)
    ('205:45.00', 'time_red')
    >>> format_duration(60001)
    ('16 h', 'time_red')
    """
    if duration is None:
        return "N/A".ljust(8), "time_green"

    if duration < 1:
        if duration < 0:
            duration = 0
        ctime = f"{duration:.6f}"
        color = "time_green"
    elif duration < 60000:
        if duration < 3:
            color = "time_yellow"
        else:
            color = "time_red"
        duration_d = timedelta(seconds=float(duration))
        mic = "%.6d" % duration_d.microseconds
        ctime = "%s:%s.%s" % (
            str((duration_d.seconds // 60)).zfill(2),
            str((duration_d.seconds % 60)).zfill(2),
            mic[:2],
        )
    else:
        ctime = "%s h" % str(int(duration / 3600))
        color = "time_red"

    return ctime, color


@limit
def processes_rows(
    term: Terminal,
    ui: UI,
    processes: Union[
        Iterable[BWProcess], Iterable[RunningProcess], Iterable[LocalRunningProcess]
    ],
    *,
    color_type: str = "default",
) -> Iterator[str]:
    """Display table rows with processes information."""

    # if color_type == 'default' and self.pid_yank.count(process['pid']) > 0:
    # color_type = 'yellow'

    def color_for(field: str) -> FormattingString:
        return getattr(term, LINE_COLORS[field][color_type])

    def template_for(column_name: str) -> str:
        return getattr(Column, column_name).value.template_h  # type: ignore

    def text_append(value: str) -> None:
        # We also restore 'normal' style so that the next item does not
        # inherit previous one's style.
        text.append(value + term.normal)

    def cell(
        process: Union[RunningProcess, BWProcess, LocalRunningProcess],
        key: str,
        crop: Optional[int],
        transform: Callable[[Any], str] = str,
        color_key: Optional[str] = None,
    ) -> None:
        column_value = transform(getattr(process, key))[:crop]
        color_key = color_key or key
        text_append(f"{color_for(color_key)}{template_for(key) % column_value}")

    flag = ui.flag
    query_mode = ui.query_mode

    for process in processes:
        text: List[str] = []
        if flag & Flag.PID:
            cell(process, "pid", None)
        if flag & Flag.DATABASE:
            cell(process, "database", 16)
        if flag & Flag.APPNAME:
            cell(process, "appname", 16)
        if flag & Flag.USER:
            cell(process, "user", 16)
        if flag & Flag.CLIENT:
            cell(process, "client", 16)
        if query_mode == QueryMode.activities:
            assert isinstance(process, LocalRunningProcess), process
            if flag & Flag.CPU:
                cell(process, "cpu", None)
            if flag & Flag.MEM:
                cell(process, "mem", None, lambda v: str(round(v, 1)))
            if flag & Flag.READ:
                cell(process, "read", None, naturalsize)
            if flag & Flag.WRITE:
                cell(process, "write", None, naturalsize)

        elif query_mode in (QueryMode.waiting, QueryMode.blocking):
            assert isinstance(process, BWProcess), process
            if flag & Flag.RELATION:
                cell(process, "relation", 9)
            if flag & Flag.TYPE:
                cell(process, "type", 16)

            if flag & Flag.MODE:
                if process.mode in (
                    "ExclusiveLock",
                    "RowExclusiveLock",
                    "AccessExclusiveLock",
                ):
                    mode_color = "mode_red"
                else:
                    mode_color = "mode_yellow"
                cell(process, "mode", 16, color_key=mode_color)

        if flag & Flag.TIME:
            ctime, color = format_duration(process.duration)
            text_append(f"{color_for(color)}{template_for('time') % ctime}")

        if query_mode == QueryMode.activities and flag & Flag.WAIT:
            assert isinstance(process, RunningProcess)
            if process.wait:
                text_append(f"{color_for('wait_red')}{template_for('wait') % 'Y'}")
            else:
                text_append(f"{color_for('wait_green')}{template_for('wait') % 'N'}")

        if (
            isinstance(process, LocalRunningProcess)
            and query_mode == QueryMode.activities
            and flag & Flag.IOWAIT
        ):
            assert process.io_wait in "YN", process.io_wait
            if process.io_wait == "Y":
                text_append(f"{color_for('wait_red')}{template_for('iowait') % 'Y'}")
            else:
                text_append(f"{color_for('wait_green')}{template_for('iowait') % 'N'}")

        state = utils.short_state(process.state)
        if state == "active":
            color_state = "state_green"
        elif state == "idle in trans":
            color_state = "state_yellow"
        elif state == "idle in trans (a)":
            color_state = "state_red"
        else:
            color_state = "state_default"
        text_append(f"{color_for(color_state)}{template_for('state') % state}")

        indent = get_indent(query_mode, flag) + " "
        dif = term.width - len(indent)

        verbose_mode = ui.verbose_mode
        if dif < 0:
            # Switch to wrap_noindent mode if terminal is too narrow.
            verbose_mode = QueryDisplayMode.wrap_noindent

        query = format_query(process.query, process.is_parallel_worker)

        if verbose_mode == QueryDisplayMode.truncate:
            text_append(" " + f"{color_for('query')}{query[:dif]}")
        else:
            query_r = f"{color_for('query')}{query}"
            if verbose_mode == QueryDisplayMode.wrap_noindent:
                if term.length(query_r.split(" ", 1)[0]) >= dif:
                    # Query too long to even start on the first line, wrap all
                    # lines.
                    query_lines = term.wrap(query_r, width=term.width)
                else:
                    # Only wrap subsequent lines.
                    wrapped_lines = term.wrap(query_r, width=dif)
                    query_lines = [" " + wrapped_lines[0]] + term.wrap(
                        " ".join(wrapped_lines[1:]), width=term.width
                    )
                text_append("\n".join(query_lines))
            else:
                assert (
                    verbose_mode == QueryDisplayMode.wrap
                ), f"unexpected mode {verbose_mode}"
                wrapped_lines = term.wrap(" " + query_r, width=dif)
                text_append(f"\n{indent}".join(wrapped_lines))

        for line in ("".join(text) + term.normal).splitlines():
            yield line


def footer(term: Terminal) -> None:
    """Display footer line."""
    query_modes_help = [
        ("/".join(keys[:-1]), qm.value) for qm, keys in KEYS_BY_QUERYMODE.items()
    ]
    assert PAUSE_KEY.name is not None
    footer_values = query_modes_help + [
        (PAUSE_KEY.name, PAUSE_KEY.description),
        (EXIT_KEY.value, EXIT_KEY.description),
        (HELP_KEY, "help"),
    ]
    width = max(len(desc) for _, desc in footer_values)
    print(
        term.ljust(
            " ".join(
                [
                    f"{key} {term.cyan_reverse(term.ljust(desc.capitalize(), width=width, fillchar=' '))}"
                    for key, desc in footer_values
                ]
            ),
            fillchar=" ",
        )
        + term.normal,
        end="",
    )


def screen(
    term: Terminal,
    ui: UI,
    *,
    host: Host,
    dbinfo: DBInfo,
    tps: int,
    active_connections: int,
    activity_stats: ActivityStats,
    render_footer: bool = True,
) -> None:
    """Display the screen."""

    processes: Union[List[RunningProcess], List[BWProcess], List[LocalRunningProcess]]
    system_info: Optional[SystemInfo]
    if isinstance(activity_stats, tuple):
        processes, system_info = activity_stats
    else:
        processes, system_info = activity_stats, None
    processes = sorted_processes(processes, key=ui.sort_key, reverse=True)  # type: ignore  # TODO: fixme

    print(term.clear + term.home, end="")
    top_height = term.height - 1
    lines_counter = line_counter(top_height)
    header(
        term,
        ui,
        host=host,
        dbinfo=dbinfo,
        tps=tps,
        active_connections=active_connections,
        system_info=system_info,
        lines_counter=lines_counter,
    )

    query_mode(term, ui, lines_counter=lines_counter)
    columns_header(term, ui, lines_counter=lines_counter)
    processes_rows(
        term,
        ui,
        processes,
        lines_counter=lines_counter,
    )
    if render_footer:
        with term.location(x=0, y=top_height):
            footer(term)
