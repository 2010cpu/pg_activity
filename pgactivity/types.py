import enum
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import attr
import psutil


T = TypeVar("T")


class Deserializable:
    """Mixin class adding deserialization support.

    >>> @attr.s(auto_attribs=True)
    ... class Point(Deserializable):
    ...     x: int
    ...     y: int
    ...     label: Optional[str] = None

    >>> data = {"x": 1, "y": 1, "label": "a"}
    >>> Point.deserialize(data)
    Point(x=1, y=1, label='a')

    >>> @attr.s(auto_attribs=True)
    ... class Line(Deserializable):
    ...     start: Point
    ...     end: Point
    ...     color: str = "black"
    ...     label: Optional[str] = None

    >>> data = {"start": {"x": 1, "y": 1}, "end": {"x": 2, "y": 2, "label": "p2"}}
    >>> Line.deserialize(data)
    Line(start=Point(x=1, y=1, label=None), end=Point(x=2, y=2, label='p2'), color='black', label=None)

    >>> data = {"start": {"x": 1, "y": 1}, "end": {"x": 2, "y": 2}, "colour": "red"}
    >>> Line.deserialize(data)
    Traceback (most recent call last):
        ...
    ValueError: unknown field(s): colour

    >>> data = {"start": {"x": 1, "y": 1}}
    >>> Line.deserialize(data)
    Traceback (most recent call last):
        ...
    ValueError: missing required field 'end'

    >>> data = {"start": {"x": 1, "y": 1}, "end": {"x": 2, "y": 2}, "color": (255, 5, 2)}
    >>> Line.deserialize(data)
    Traceback (most recent call last):
        ...
    TypeError: invalid type for field 'color', expecting <class 'str'>
    """

    @classmethod
    def deserialize(cls: Type[T], data: Mapping[str, Any]) -> T:
        args = {}
        for field in attr.fields(cls):
            name = field.name
            try:
                value = data[name]
            except KeyError:
                if field.default != attr.NOTHING:
                    continue
                raise ValueError(f"missing required field '{name}'") from None
            else:
                try:
                    deserializer = getattr(field.type, "deserialize")
                except AttributeError:
                    assert field.type is not None, "fields should be typed"
                    try:
                        is_subtype = isinstance(value, field.type)
                    except TypeError:
                        # This might happen for Union types (e.g.
                        # Optional[X]), we assume the type is okay waiting for
                        # a better strategy.
                        pass
                    else:
                        if not is_subtype:
                            raise TypeError(
                                f"invalid type for field '{name}', expecting {field.type}"
                            ) from None
                else:
                    value = deserializer(value)

                args[name] = value

        unknown = set(data) - set(args)
        if unknown:
            raise ValueError(
                f"unknown field(s): {', '.join(sorted(unknown))}"
            ) from None

        return cls(**args)  # type: ignore


E = TypeVar("E", bound=enum.IntEnum)


def enum_next(e: E) -> E:
    """Return an increment value of given enum.

    >>> class Seasons(enum.IntEnum):
    ...     winter = 1
    ...     spring = 2
    ...     summer = 3
    ...     autumn = 4

    >>> enum_next(Seasons.winter)
    <Seasons.spring: 2>
    >>> enum_next(Seasons.spring)
    <Seasons.summer: 3>
    >>> enum_next(Seasons.autumn)
    <Seasons.winter: 1>
    """
    return e.__class__((e.value % max(e.__class__)) + 1)


@enum.unique
class Flag(enum.IntFlag):
    """Column flag.

    >>> f = Flag(3)
    >>> f
    <Flag.APPNAME|DATABASE: 3>
    >>> f | Flag.CLIENT
    <Flag.CLIENT|APPNAME|DATABASE: 7>
    >>> f ^= Flag.APPNAME
    >>> f
    <Flag.DATABASE: 1>
    """

    DATABASE = 1
    APPNAME = 2
    CLIENT = 4
    USER = 8
    CPU = 16
    MEM = 32
    READ = 64
    WRITE = 128
    TIME = 256
    WAIT = 512
    RELATION = 1024
    TYPE = 2048
    MODE = 4096
    IOWAIT = 8192
    PID = 16384

    @classmethod
    def from_options(
        cls,
        *,
        is_local: bool,
        noappname: bool,
        noclient: bool,
        nocpu: bool,
        nodb: bool,
        nomem: bool,
        nopid: bool,
        noread: bool,
        notime: bool,
        nouser: bool,
        nowait: bool,
        nowrite: bool,
        **kwargs: Any,
    ) -> "Flag":
        """Build a Flag value from command line options.

        >>> options = {
        ... 'noappname': False,
        ... 'noclient': False,
        ... 'nocpu': False,
        ... 'nodb': False,
        ... 'nomem': False,
        ... 'nopid': False,
        ... 'noread': False,
        ... 'notime': False,
        ... 'nouser': False,
        ... 'nowait': False,
        ... 'nowrite': False,
        ... }
        >>> Flag.from_options(is_local=True, **options)
        <Flag.PID|IOWAIT|MODE|TYPE|RELATION|WAIT|TIME|WRITE|READ|MEM|CPU|USER|CLIENT|APPNAME|DATABASE: 32767>
        >>> Flag.from_options(is_local=False, **options)
        <Flag.PID|MODE|TYPE|RELATION|WAIT|TIME|USER|CLIENT|APPNAME|DATABASE: 24335>
        >>> options['nodb'] = True
        >>> options['notime'] = True
        >>> options['nopid'] = True
        >>> Flag.from_options(is_local=False, **options)
        <Flag.MODE|TYPE|RELATION|WAIT|USER|CLIENT|APPNAME: 7694>
        """
        flag = cls(sum(cls))
        if nodb:
            flag ^= cls.DATABASE
        if nouser:
            flag ^= cls.USER
        if nocpu:
            flag ^= cls.CPU
        if noclient:
            flag ^= cls.CLIENT
        if nomem:
            flag ^= cls.MEM
        if noread:
            flag ^= cls.READ
        if nowrite:
            flag ^= cls.WRITE
        if notime:
            flag ^= cls.TIME
        if nowait:
            flag ^= cls.WAIT
        if noappname:
            flag ^= cls.APPNAME
        if nopid:
            flag ^= cls.PID

        # Remove some if no running against local pg server.
        if not is_local and (flag & cls.CPU):
            flag ^= cls.CPU
        if not is_local and (flag & cls.MEM):
            flag ^= cls.MEM
        if not is_local and (flag & cls.READ):
            flag ^= cls.READ
        if not is_local and (flag & cls.WRITE):
            flag ^= cls.WRITE
        if not is_local and (flag & cls.IOWAIT):
            flag ^= cls.IOWAIT
        return flag


class SortKey(enum.Enum):
    cpu = enum.auto()
    mem = enum.auto()
    read = enum.auto()
    write = enum.auto()
    duration = enum.auto()

    @classmethod
    def default(cls) -> "SortKey":
        return cls.duration


@enum.unique
class QueryDisplayMode(enum.IntEnum):
    truncate = 1
    wrap_noindent = 2
    wrap = 3

    @classmethod
    def default(cls) -> "QueryDisplayMode":
        return cls.wrap_noindent


@enum.unique
class QueryMode(enum.Enum):
    activities = "running queries"
    waiting = "waiting queries"
    blocking = "blocking queries"

    @classmethod
    def default(cls) -> "QueryMode":
        return cls.activities


@enum.unique
class DurationMode(enum.IntEnum):
    query = 1
    transaction = 2
    backend = 3


@attr.s(auto_attribs=True, frozen=True, slots=True)
class Column:
    """A column in stats table.

    >>> c = Column("pid", "PID", "%-6s", True, SortKey.cpu, max_width=6)
    >>> c.title_render()
    'PID   '
    >>> c.title_color(SortKey.cpu)
    'cyan'
    >>> c.title_color(SortKey.duration)
    'green'
    >>> c.render('1234')
    '1234  '
    >>> c.render('12345678')
    '123456'
    """

    key: str = attr.ib(repr=False)
    name: str
    template_h: str = attr.ib()
    mandatory: bool = False
    sort_key: Optional[SortKey] = None
    max_width: Optional[int] = attr.ib(default=None, repr=False)

    @template_h.validator
    def _template_h_is_a_format_string_(self, attribute: Any, value: str) -> None:
        """Validate template_h attribute.

        >>> Column("k", "a", "b%%aa")
        Traceback (most recent call last):
            ...
        ValueError: template_h must be a format string with one placeholder
        >>> Column("k", "a", "baad")
        Traceback (most recent call last):
            ...
        ValueError: template_h must be a format string with one placeholder
        >>> Column("k", "a", "%s is good")  # doctest: +ELLIPSIS
        Column(name='a', template_h='%s is good', ...)
        """
        if value.count("%") != 1:
            raise ValueError(
                f"{attribute.name} must be a format string with one placeholder"
            )

    def title_render(self) -> str:
        return self.template_h % self.name

    def title_color(self, sort_by: SortKey) -> str:
        if self.sort_key == sort_by:
            return "cyan"  # TODO: define a Color enum
        return "green"

    def render(self, value: str) -> str:
        return self.template_h % value[: self.max_width]


@attr.s(auto_attribs=True, frozen=True, slots=True)
class UI:
    """State of the UI."""

    columns_by_querymode: Mapping[QueryMode, Tuple[Column, ...]]
    flag: Flag
    min_duration: float = 0.0
    duration_mode: DurationMode = attr.ib(
        default=DurationMode.query, converter=DurationMode
    )
    verbose_mode: QueryDisplayMode = attr.ib(
        default=QueryDisplayMode.default(), converter=QueryDisplayMode
    )
    sort_key: SortKey = attr.ib(default=SortKey.default(), converter=SortKey)
    query_mode: QueryMode = attr.ib(default=QueryMode.activities, converter=QueryMode)
    refresh_time: float = 2.0
    in_pause: bool = False

    @classmethod
    def make(
        cls,
        flag: Flag = Flag(sum(Flag)),
        *,
        max_db_length: int = 16,
        **kwargs: Any,
    ) -> "UI":
        possible_columns: Dict[str, Column] = {}

        def add_column(key: str, **kwargs: Any) -> None:
            assert key not in possible_columns, f"duplicated key {key}"
            possible_columns[key] = Column(key, **kwargs)

        if Flag.APPNAME & flag:
            add_column(
                key="appname",
                name="APP",
                template_h="%16s ",
                max_width=16,
            )
        if Flag.CLIENT & flag:
            add_column(
                key="client",
                name="CLIENT",
                template_h="%16s ",
                max_width=16,
            )
        if Flag.CPU & flag:
            add_column(
                key="cpu",
                name="CPU%",
                template_h="%6s ",
                sort_key=SortKey.cpu,
            )
        if Flag.DATABASE & flag:
            add_column(
                key="database",
                name="DATABASE",
                template_h=f"%-{max_db_length}s ",
                sort_key=None,
                max_width=16,
            )
        if Flag.IOWAIT & flag:
            add_column(key="iowait", name="IOW", template_h="%4s ")
        if Flag.MEM & flag:
            add_column(
                key="mem",
                name="MEM%",
                template_h="%4s ",
                sort_key=SortKey.mem,
            )
        if Flag.MODE & flag:
            add_column(key="mode", name="MODE", template_h="%16s ", max_width=16)
        if Flag.PID & flag:
            add_column(key="pid", name="PID", template_h="%-6s ")
        add_column(key="query", name="Query", template_h=" %2s")
        if Flag.READ & flag:
            add_column(
                key="read",
                name="READ/s",
                template_h="%8s ",
                sort_key=SortKey.read,
            )
        if Flag.RELATION & flag:
            add_column(
                key="relation",
                name="RELATION",
                template_h="%9s ",
                max_width=9,
            )
        add_column(key="state", name="state", template_h=" %17s  ")
        if Flag.TIME & flag:
            add_column(
                key="time",
                name="TIME+",
                template_h="%9s ",
                sort_key=SortKey.duration,
            )
        if Flag.TYPE & flag:
            add_column(key="type", name="TYPE", template_h="%16s ", max_width=16)
        if Flag.USER & flag:
            add_column(key="user", name="USER", template_h="%16s ", max_width=16)
        if Flag.WAIT & flag:
            add_column(key="wait", name="W", template_h="%2s ")
        if Flag.WRITE & flag:
            add_column(
                key="write",
                name="WRITE/s",
                template_h="%8s ",
            )

        columns_key_by_querymode: Mapping[QueryMode, List[str]] = {
            QueryMode.activities: [
                "pid",
                "database",
                "appname",
                "user",
                "client",
                "cpu",
                "mem",
                "read",
                "write",
                "time",
                "wait",
                "iowait",
                "state",
                "query",
            ],
            QueryMode.waiting: [
                "pid",
                "database",
                "appname",
                "user",
                "client",
                "relation",
                "type",
                "mode",
                "time",
                "state",
                "query",
            ],
            QueryMode.blocking: [
                "pid",
                "database",
                "appname",
                "user",
                "client",
                "relation",
                "type",
                "mode",
                "time",
                "state",
                "query",
            ],
        }

        def make_columns_for(query_mode: QueryMode) -> Iterator[Column]:
            for key in columns_key_by_querymode[query_mode]:
                try:
                    yield possible_columns[key]
                except KeyError:
                    pass

        columns_by_querymode = {qm: tuple(make_columns_for(qm)) for qm in QueryMode}
        return cls(columns_by_querymode=columns_by_querymode, flag=flag, **kwargs)

    def evolve(self, **changes: Any) -> "UI":
        """Return a new UI with 'changes' applied.

        >>> ui = UI.make()
        >>> ui.query_mode.value
        'running queries'
        >>> new_ui = ui.evolve(query_mode=QueryMode.blocking)
        >>> new_ui.query_mode.value
        'blocking queries'
        """
        assert "flag" not in changes, "cannot evolve with a new flag"
        return attr.evolve(self, **changes)

    def column(self, key: str) -> Column:
        """Return the column matching 'key'.

        >>> ui = UI.make()
        >>> ui.column("cpu")
        Column(name='CPU%', template_h='%6s ', mandatory=False, sort_key=<SortKey.cpu: 1>)
        >>> ui.column("gloups")
        Traceback (most recent call last):
          ...
        ValueError: gloups
        """
        for column in self.columns_by_querymode[self.query_mode]:
            if column.key == key:
                return column
        else:
            raise ValueError(key)

    def columns(self) -> Tuple[Column, ...]:
        """Return the tuple of Column for current mode.

        >>> flag = Flag.PID | Flag.DATABASE | Flag.APPNAME | Flag.RELATION
        >>> ui = UI.make(flag=flag)
        >>> [c.name for c in ui.columns()]
        ['PID', 'DATABASE', 'APP', 'state', 'Query']
        """
        return self.columns_by_querymode[self.query_mode]


@attr.s(auto_attribs=True, frozen=True, slots=True)
class Host:
    pg_version: str
    hostname: str
    user: str
    host: str
    port: int
    dbname: str


@attr.s(auto_attribs=True, slots=True)
class DBInfo:
    total_size: int
    size_ev: int


@attr.s(auto_attribs=True, slots=True)
class MemoryInfo:
    percent: float
    used: int
    total: int

    @classmethod
    def default(cls) -> "MemoryInfo":
        return cls(0.0, 0, 0)


@attr.s(auto_attribs=True, slots=True)
class LoadAverage:
    avg1: float
    avg5: float
    avg15: float

    @classmethod
    def default(cls) -> "LoadAverage":
        return cls(0.0, 0.0, 0.0)


@attr.s(auto_attribs=True, frozen=True, slots=True)
class IOCounter(Deserializable):
    count: int
    bytes: int
    chars: int = 0

    @classmethod
    def default(cls) -> "IOCounter":
        return cls(0, 0)


@attr.s(auto_attribs=True, frozen=True, slots=True)
class SystemInfo:
    memory: MemoryInfo
    swap: MemoryInfo
    load: LoadAverage
    io_read: IOCounter
    io_write: IOCounter
    max_iops: int = 0

    @classmethod
    def default(
        cls,
        *,
        memory: Optional[MemoryInfo] = None,
        swap: Optional[MemoryInfo] = None,
        load: Optional[LoadAverage] = None,
    ) -> "SystemInfo":
        """Zero-value builder.

        >>> SystemInfo.default()  # doctest: +NORMALIZE_WHITESPACE
        SystemInfo(memory=MemoryInfo(percent=0.0, used=0, total=0),
                   swap=MemoryInfo(percent=0.0, used=0, total=0),
                   load=LoadAverage(avg1=0.0, avg5=0.0, avg15=0.0),
                   io_read=IOCounter(count=0, bytes=0, chars=0),
                   io_write=IOCounter(count=0, bytes=0, chars=0),
                   max_iops=0)
        """
        return cls(
            memory or MemoryInfo.default(),
            swap or MemoryInfo.default(),
            load or LoadAverage.default(),
            IOCounter.default(),
            IOCounter.default(),
        )


class LockType(enum.Enum):
    """Type of lockable object

    https://www.postgresql.org/docs/current/view-pg-locks.html
    """

    relation = enum.auto()
    extend = enum.auto()
    page = enum.auto()
    tuple = enum.auto()
    transactionid = enum.auto()
    virtualxid = enum.auto()
    object = enum.auto()
    userlock = enum.auto()
    advisory = enum.auto()

    def __str__(self) -> str:
        # Custom str(self) for transparent rendering in views.
        return self.name


def locktype(value: str) -> LockType:
    try:
        return LockType[value]
    except KeyError as exc:
        raise ValueError(f"invalid lock type {exc}") from None


@attr.s(auto_attribs=True, slots=True)
class BaseProcess:
    pid: int
    appname: str
    database: str
    user: str
    client: str
    duration: float
    state: str
    query: str


@attr.s(auto_attribs=True, frozen=True, slots=True)
class RunningProcess(BaseProcess, Deserializable):
    """Process for a running query."""

    wait: bool
    is_parallel_worker: bool


@attr.s(auto_attribs=True, frozen=True, slots=True)
class BWProcess(BaseProcess):
    """Process for a blocking or waiting query."""

    # Lock information from pg_locks view
    # https://www.postgresql.org/docs/current/view-pg-locks.html
    mode: str
    type: LockType = attr.ib(converter=locktype)
    relation: str

    # TODO: update queries to select/compute this column.
    is_parallel_worker: bool = attr.ib(default=False, init=False)


@attr.s(auto_attribs=True, frozen=True, slots=True)
class SystemProcess(Deserializable):
    meminfo: Tuple[int, ...]
    io_read: IOCounter
    io_write: IOCounter
    io_time: float
    mem_percent: float
    cpu_percent: float
    cpu_times: Tuple[float, ...]
    read_delta: float
    write_delta: float
    io_wait: str
    psutil_proc: Optional[psutil.Process]


@attr.s(auto_attribs=True, frozen=True, slots=True)
class LocalRunningProcess(RunningProcess):
    cpu: float
    mem: float
    read: float
    write: float
    io_wait: str

    @classmethod
    def from_process(
        cls, process: RunningProcess, **kwargs: Union[float, str]
    ) -> "LocalRunningProcess":
        return cls(**dict(attr.asdict(process), **kwargs))


LocalProcesses = Tuple[Union[List[BWProcess], List[LocalRunningProcess]], SystemInfo]
ActivityStats = Union[List[RunningProcess], List[BWProcess], LocalProcesses]

ProcessSet = Union[List[LocalRunningProcess], List[RunningProcess], List[BWProcess]]
