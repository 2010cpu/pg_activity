import enum
from typing import (
    Any,
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
                raise ValueError(f"missing required field '{name}'")
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
                            )
                else:
                    value = deserializer(value)

                args[name] = value

        unknown = set(data) - set(args)
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")

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
        ... 'noread': False,
        ... 'notime': False,
        ... 'nouser': False,
        ... 'nowait': False,
        ... 'nowrite': False,
        ... }
        >>> Flag.from_options(is_local=True, **options)
        <Flag.IOWAIT|MODE|TYPE|RELATION|WAIT|TIME|WRITE|READ|MEM|CPU|USER|CLIENT|APPNAME|DATABASE: 16383>
        >>> Flag.from_options(is_local=False, **options)
        <Flag.MODE|TYPE|RELATION|WAIT|TIME|USER|CLIENT|APPNAME|DATABASE: 7951>
        >>> options['nodb'] = True
        >>> options['notime'] = True
        >>> Flag.from_options(is_local=False, **options)
        <Flag.MODE|TYPE|RELATION|WAIT|USER|CLIENT|APPNAME: 7694>
        """
        flag = (
            cls.DATABASE
            | cls.USER
            | cls.CLIENT
            | cls.CPU
            | cls.MEM
            | cls.READ
            | cls.WRITE
            | cls.TIME
            | cls.WAIT
            | cls.RELATION
            | cls.TYPE
            | cls.MODE
            | cls.IOWAIT
            | cls.APPNAME
        )
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


@attr.s(auto_attribs=True, frozen=True, slots=True)
class ColumnTitle:
    """Title of a column in stats table.

    >>> c = ColumnTitle("PID", "%-6s", None, True, SortKey.cpu)
    >>> c.render()
    'PID   '
    >>> c.color(SortKey.cpu)
    'cyan'
    >>> c.color(SortKey.duration)
    'green'
    """

    name: str
    template_h: str = attr.ib()
    flag: Optional[Flag]
    mandatory: bool
    sort_key: Optional[SortKey] = None

    @template_h.validator
    def _template_h_is_a_format_string_(self, attribute: Any, value: str) -> None:
        """Validate template_h attribute.

        >>> ColumnTitle("a", "b%%aa", Flag.DATABASE, False)
        Traceback (most recent call last):
            ...
        ValueError: template_h must be a format string with one placeholder
        >>> ColumnTitle("a", "baad", Flag.DATABASE, False)
        Traceback (most recent call last):
            ...
        ValueError: template_h must be a format string with one placeholder
        >>> ColumnTitle("a", "%s is good", Flag.DATABASE, False)  # doctest: +ELLIPSIS
        ColumnTitle(name='a', template_h='%s is good', flag=<Flag.DATABASE: 1>, ...)
        """
        if value.count("%") != 1:
            raise ValueError(
                f"{attribute.name} must be a format string with one placeholder"
            )

    def render(self) -> str:
        return self.template_h % self.name

    def color(self, sort_by: SortKey) -> str:
        if self.sort_key == sort_by:
            return "cyan"  # TODO: define a Color enum
        return "green"


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


class QueryDisplayMode(enum.IntEnum):
    truncate = 1
    wrap_noindent = 2
    wrap = 3

    @classmethod
    def default(cls) -> "QueryDisplayMode":
        return cls.wrap_noindent


class QueryMode(enum.Enum):
    activities = "running queries"
    waiting = "waiting queries"
    blocking = "blocking queries"

    @classmethod
    def default(cls) -> "QueryMode":
        return cls.activities


class DurationMode(enum.IntEnum):
    query = 1
    transaction = 2
    backend = 3


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
                   io_write=IOCounter(count=0, bytes=0, chars=0))
        """
        return cls(
            memory or MemoryInfo.default(),
            swap or MemoryInfo.default(),
            load or LoadAverage.default(),
            IOCounter.default(),
            IOCounter.default(),
        )


@attr.s(auto_attribs=True, slots=True)
class ProcessExtras(Deserializable):
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
    is_parallel_worker: bool
    appname: str


@attr.s(auto_attribs=True, slots=True)
class Process(Deserializable):
    """Simple class for process management.

    >>> data = {
    ...     "database" : "pgbench",
    ...     "read" : None,
    ...     "duration" : -0.003353,
    ...     "mem" : None,
    ...     "query" : "END;",
    ...     "cpu" : None,
    ...     "pid" : 6229,
    ...     "appname" : "pgbench",
    ...     "wait" : True,
    ...     "client" : "local",
    ...     "state" : "active",
    ...     "user" : "postgres",
    ...     "write" : None,
    ...     "extras" : {
    ...        "is_parallel_worker" : False,
    ...        "read_delta" : 0.0,
    ...        "io_time" : 1596806345.17465,
    ...        "appname" : "pgbench",
    ...        "psutil_proc" : None,
    ...        "io_wait" : "N",
    ...        "io_read" : {
    ...           "count" : 805,
    ...           "bytes" : 184320,
    ...           "chars" : 5928507,
    ...        },
    ...        "io_write" : {
    ...           "count" : 408,
    ...           "bytes" : 4702208,
    ...           "chars" : 4866103,
    ...        },
    ...        "cpu_percent" : 0.0,
    ...        "mem_percent" : 1.03052852888703,
    ...        "meminfo" : [
    ...           63643648,
    ...           219631616,
    ...           61329408,
    ...           4608000,
    ...           0,
    ...           2908160,
    ...           0
    ...        ],
    ...        "write_delta" : 0.0,
    ...        "cpu_times" : [
    ...           0.25,
    ...           0.06,
    ...           0,
    ...           0,
    ...           0.04
    ...        ]
    ...     }
    ... }
    >>> Process.deserialize(data)  # doctest: +ELLIPSIS
    Process(pid=6229, database='pgbench', user='postgres', client='local', duration=-0.003353, wait=True, ...)
    """

    pid: int
    database: str
    user: str
    client: str
    duration: float
    wait: bool
    query: str
    state: str
    appname: str  # TODO: rename as application_name
    extras: ProcessExtras
    cpu: Optional[float] = None
    mem: Optional[float] = None
    read: Optional[float] = None
    write: Optional[float] = None


class DictSequenceProxy:
    """Proxy class for Dict and Sequence protocols.

    >>> @attr.s(auto_attribs=True)
    ... class A(DictSequenceProxy):
    ...     x: str

    >>> a = A("x")
    >>> a[0]
    'x'
    >>> a["x"]
    'x'

    >>> a["y"]
    Traceback (most recent call last):
        ...
    KeyError: 'y'
    >>> a[42]
    Traceback (most recent call last):
        ...
    IndexError: 42
    >>> a[[]]
    Traceback (most recent call last):
        ...
    TypeError: expecting a string or int key
    """

    def __getitem__(self, key: Union[int, str]) -> Any:
        if isinstance(key, str):
            try:
                return getattr(self, key)
            except AttributeError:
                raise KeyError(key) from None
        elif isinstance(key, int):
            seq = attr.astuple(self)
            try:
                return seq[key]
            except IndexError:
                raise IndexError(key) from None
        else:
            raise TypeError("expecting a string or int key")


@attr.s(auto_attribs=True, frozen=True, slots=True)
class Activity(DictSequenceProxy):
    """Result from pg_stat_activity view query."""

    pid: int
    application_name: str  # TODO: change queries to return 'appname' directly
    appname: str = attr.ib(init=False)
    database: str
    client: str
    duration: float
    wait: bool
    user: str
    state: str
    query: str
    is_parallel_worker: bool

    def __attrs_post_init__(self) -> None:
        # Work around instance being frozen, per attrs documentation.
        object.__setattr__(self, "appname", self.application_name)


@attr.s(auto_attribs=True, frozen=True, slots=True)
class ActivityBW(DictSequenceProxy):
    """Result from pg_stat_activity view query for blocking/waiting queries."""

    pid: int
    appname: str
    database: str
    user: str
    mode: str  # TODO: enum
    type: str  # TODO: enum
    relation: str
    duration: float
    state: str
    query: str

    @property
    def is_parallel_worker(self) -> bool:
        # TODO: update queries to select/compute this column.
        return False


@attr.s(auto_attribs=True, frozen=True, slots=True)
class ActivityProcess:
    pid: int
    appname: str
    database: str
    user: str
    client: str
    cpu: float
    mem: float
    read: float
    write: float
    state: str
    query: str
    duration: Optional[float]
    wait: bool
    io_wait: str
    is_parallel_worker: bool
