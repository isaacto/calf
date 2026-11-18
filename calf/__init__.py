"""Calf: Command Argument Loading Functions

Allow functions to be written naturally while capable of loading
parameters from command line arguments.

"""

# N.B.: To avoid having to say a mouthful of words like "function
# argument" and "command line argument", they are called simply
# "params" and "args" respectively here.

import argparse
import collections.abc as ca
import dataclasses
import datetime
import inspect
import itertools
import re
import sys
import typing


__version__ = '0.5'


ConverterType = ca.Callable[[str], typing.Any]


def _time_convert(s: str) -> datetime.time:
    try:
        return datetime.datetime.strptime(s, '%H:%M').time()
    except ValueError:
        return datetime.datetime.strptime(s, '%H:%M:%S').time()


def _datetime_convert(s: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M')
    except ValueError:
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')


def _bool_convert(s: str) -> bool:
    if s == '0':
        return False
    if s == '1':
        return True
    raise ValueError(s)


CONVERTERS: dict[type, ConverterType] = {
    bool: _bool_convert,
    datetime.date: lambda s: datetime.datetime.strptime(s, '%Y-%m-%d').date(),
    datetime.time: _time_convert,
    datetime.datetime: _datetime_convert,
}
"Add or change a function here if you want to teach calf how to read a type"


@dataclasses.dataclass
class ParamInfo:
    "Parameter information extracted from doc-strings"
    desc: str
    "The description of the parameter"
    short: str = ''
    "The short option string, like '-i'"
    choices: typing.Optional[list[str]] = None
    "The possible choices"


DocParserRetType = tuple[str, dict[str, ParamInfo]]
DocParserType = ca.Callable[[str], DocParserRetType]


def plain_doc_parser(doc: str) -> DocParserRetType:
    """A doc parser which simply strip spaces

    Args:

        doc: The function doc string

    Returns:

        The parsed doc string and empty parameter list

    """
    return inspect.cleandoc(doc), {}


def google_doc_parser(doc: str) -> DocParserRetType:
    """A doc parser handling Google-style docstrings

    Args:

        doc: The function doc string

    Returns:

        The parsed doc string and parsed parameter list

    """
    main_doc, param_docs = plain_doc_parser(doc)
    # Split main part from other sections
    parts = re.split(r'(^(?:Args?|Returns?|Raises?|Yields?|Examples?|'
                     r'Attributes?):\s*$)',
                     main_doc, 1, re.M)
    if len(parts) <= 1:
        return main_doc, param_docs
    main_doc = parts[0]
    remain = ''.join(parts[1:])  # Combine the separator and the text
    # Skip before Args section
    parts = re.split(r'^Args?:\s*$', remain, 1, re.M)
    if len(parts) <= 1:
        return main_doc, param_docs
    for group in indented_groups(parts[1]):
        # Split name from description of option
        arg = ' '.join(group)
        name, _sep, desc = arg.partition(':')
        name = re.split(r'[\ \(]', name.strip())[0]
        param_docs[name] = ParamInfo(desc=desc.strip())
    return main_doc, param_docs


def sphinx_doc_parser(doc: str) -> DocParserRetType:
    """A doc parser handling Sphinx-style and epydoc-style docstrings

    Args:

        doc: The function doc string

    Returns:

        The parsed doc string and parsed parameter list

    """
    main_doc, param_docs = plain_doc_parser(doc)
    parts = re.split(r'(^[:@].*:)', main_doc, 1, re.M)
    if len(parts) <= 1:
        return main_doc, param_docs
    main_doc = parts[0]
    for group in indented_groups(''.join(parts[1:])):
        if not (match := re.match(r'[:@]param\s+([^:]+):\s*(.*)$',
                                  ' '.join(group))):
            continue
        name = match.group(1).strip('`').lstrip('*')
        param_docs[name] = ParamInfo(match.group(2).strip())
    return main_doc, param_docs


def numpy_doc_parser(doc: str) -> DocParserRetType:
    """A doc parser handling Numpy-style docstrings

    Args:

        doc: The function doc string

    Returns:

        The parsed doc string and parsed parameter list

    """
    main_doc, param_docs = plain_doc_parser(doc)
    parts = re.split(r'\s*([^\n]+\n\s*\s*-+\s*\n)', main_doc)
    if len(parts) <= 1:
        return main_doc, param_docs
    main_doc = parts.pop(0)
    while len(parts) >= 2:
        header = parts[0]
        value = parts[1]
        parts[0:2] = []
        if not re.match(r'parameters?\s*\n', header, re.I):
            continue
        for group in indented_groups(value):
            name = group[0].split(':')[0].strip()
            param_docs[name] = ParamInfo(
                ' '.join(l.strip() for l in group[1:]))
    return main_doc, param_docs


def indented_groups(inp: str) -> ca.Iterator[list[str]]:
    """Split text according to indentation

    Args:

        inp: The input text.  Lines after the first one dedenting over
            the first line are ignored, as well as lines containing
            only whitespaces.

    Yields:

        List of lines of each group.  The first of each of them should
            be indented less than all the remainder.

    """
    lines = [l.expandtabs() for l in inp.split('\n') if l.strip()]
    if not lines:
        return
    ilen = len(lines[0]) - len(lines[0].lstrip(' '))
    lines = list(itertools.takewhile(lambda x: x.startswith(' ' * ilen),
                                     lines))
    is_start = [0 if l[ilen] == ' ' else 1 for l in lines]
    group_cnt = list(itertools.accumulate(is_start))
    for _, group_iter in itertools.groupby(zip(lines, group_cnt),
                                           lambda x: x[1]):
        yield list(x for x, _ in group_iter)


ParamParserType = ca.Callable[[ParamInfo], None]


def basic_param_parser(pinfo: ParamInfo) -> None:
    """Basic parameter calf-specific doc-string parser

    Extract a leading "(-x)" as short option, and trailing "{...,
    ...}" as choices in parameter doc string.  The short option is
    removed from the parameter description as argparse shows it.

    Args:

        pinfo: The parameter information

    """
    if match := re.match(r'^\((-[A-Za-z0-9])\)\s*(.*)', pinfo.desc):
        pinfo.desc = match.group(2)
        pinfo.short = match.group(1)
    if (match := re.match(r'^(.*?) *\{([^{}]*)\}([.,;]?)$', pinfo.desc)) \
       and ',' in match.group(2):
        pinfo.choices = [x.strip() for x in re.split(r',\s*', match.group(2))]
        pinfo.desc = match.group(1) + match.group(3)
    pinfo.desc = pinfo.desc.strip()


FuncType = ca.Callable[..., typing.Any]


NO_DEFAULT = object()


def unwrap_optional(ptype: type, default: typing.Any) \
        -> tuple[type, typing.Any]:
    """Look through a parameterized Optional parameter type

    A parameterized Optional without a default provides no value, which
    is the same as defaulting to None, so the two are made the same here.

    Args:

        ptype: The parameter type
        default: The parameter default, or NO_DEFAULT

    Returns:

        The type the Optional wraps, or ptype itself if it is not one,
        and the default, which becomes None for an Optional parameter
        without one

    """
    if typing.get_origin(ptype) is typing.Union:
        pargs = typing.get_args(ptype)
        if len(pargs) == 2 and pargs[1] is type(None):
            return pargs[0], None if default is NO_DEFAULT else default
    return ptype, default


class _BlindParser(argparse.ArgumentParser):
    "Parser blind to the variable arguments, printing its holder's text"

    def __init__(self, holder: 'CalfParser',
                 **kwargs: typing.Any) -> None:
        super().__init__(**kwargs)
        self._holder = holder

    def format_usage(self) -> str:
        return self._holder.format_usage()

    def format_help(self) -> str:
        return self._holder.format_help()


class CalfParser(argparse.ArgumentParser):
    """Argument parser which parses with a parser knowing no var args

    This is the parser calf creates, the one the loaders add their
    arguments to, and the one the command line is parsed with: it
    documents the whole command line itself, while the blind parser it
    holds does the parsing.  add_argument passes an argument to that
    parser, so that it is parsed as well as documented, except one
    declared with nargs='*': such is the argument of a
    variable-length parameter, whose values the VarArgBroker
    distributes, and the blind parser must not consume them; it is
    documented here only, so parse_known_args leaves their tokens over
    as the remaining arguments.  The blind parser borrows this
    parser's text, so its help and its errors still describe the whole
    command line.

    Args:

        kwargs: The arguments of the parser to create

    """

    def __init__(self, **kwargs: typing.Any) -> None:
        # The blind parser comes first: the parent constructor adds the
        # help argument through add_argument, which already needs it.
        # The blind parser does not add a help argument of its own, as
        # the forwarded one registers it later on.
        self._blind = _BlindParser(self, **{**kwargs, 'add_help': False})
        super().__init__(**kwargs)

    def add_argument(self, *args: typing.Any, **kwargs: typing.Any) \
            -> argparse.Action:
        """Add an argument, to the blind parser too if it must be parsed

        An argument taking a variable number of values (nargs='*')
        belongs to a variable-length parameter and is only documented,
        as its values are distributed by the VarArgBroker.
        """
        action = super().add_argument(*args, **kwargs)
        if kwargs.get('nargs') != '*':
            self._blind.add_argument(*args, **kwargs)
        return action

    # Narrow argparse's generic Namespace type argument on purpose:
    # calf always parses into a plain argparse.Namespace
    def parse_args(  # type: ignore[override]
            self, args: typing.Optional[ca.Sequence[str]] = None,
            namespace: typing.Optional[argparse.Namespace] = None) \
            -> argparse.Namespace:
        return self._blind.parse_args(args, namespace)

    def parse_known_args(  # type: ignore[override]
            self, args: typing.Optional[ca.Sequence[str]] = None,
            namespace: typing.Optional[argparse.Namespace] = None) \
            -> tuple[argparse.Namespace, list[str]]:
        return self._blind.parse_known_args(args, namespace)


class CalfRunner:
    """Convert callables to ArgumentParser and use it to provide a CLI

    Args:

        selectors: The selectors to match parameters and create loaders
        doc_parser: How to parse the docstring
        param_parser: How to parse the parameter string in the docstring

    """
    def __init__(self, selectors: ca.Iterable['LoaderSelector'],
                 doc_parser: DocParserType,
                 param_parser: ParamParserType) -> None:
        self._selectors = list(selectors) + [LoaderSelector()]
        self._doc_parser = doc_parser
        self._param_parser = param_parser

    def __call__(self, func: FuncType,
                 args: typing.Optional[ca.Sequence[str]] = None,
                 prog: typing.Optional[str] = None) \
            -> typing.Any:
        """Convert func to a parser, collect arguments and call func

        Args:

            func: The function to convert and call
            args: The command line arguments, use sys.argv if None
            prog: The program name

        Returns:

            Whatever func returns

        """
        calf_info = self.get_calf(func, prog)
        namespace = self.parse_args(
            calf_info, sys.argv[1:] if args is None else args)
        pos, kwd = self.ns2params(calf_info, namespace)
        return func(*pos, **kwd)

    def get_calf(self, func: FuncType,
                 prog: typing.Optional[str] = None) -> 'CalfInfo':
        """Get calf information object

        Parse the docstring of func and inspect its parameters to
        create an argument parser that would create a command line
        interface to the function.  These are put into a CalfInfo
        object for later uses.

        Args:

            func: The function to get parser for

        Returns:

            Calf information, which includes the parser as well as
            other information collected

        """
        calf_info = CalfInfo()
        calf_info.usage, calf_info.param_info \
            = self._doc_parser(func.__doc__ or '')
        for pinfo in calf_info.param_info.values():
            self._param_parser(pinfo)
        self.create_arg_parser(calf_info, prog)
        specs = calf_info.param_specs = inspect.getfullargspec(func)
        # A parameter which cannot be given by name has to take a
        # positional slot when calling the function: the positional-only
        # ones, and, as a var-arg parameter never takes a keyword, every
        # parameter in front of it
        calf_info.positional_params = (
            list(specs.args) if specs.varargs else
            [name for name, param
             in inspect.signature(func).parameters.items()
             if param.kind is inspect.Parameter.POSITIONAL_ONLY])
        params = specs.args or []
        defaults = list(specs.defaults or ())
        defaults = [NO_DEFAULT] * (len(params) - len(defaults)) + defaults
        for param, default in zip(params, defaults):
            self.add_param(calf_info, param, default, 'pos')
        for param in specs.kwonlyargs:
            self.add_param(calf_info, param,
                           (specs.kwonlydefaults or {}).get(param, NO_DEFAULT),
                           'opt')
        if specs.varkw:
            self.add_param(calf_info, specs.varkw, NO_DEFAULT, 'varkw')
        if specs.varargs:
            self.add_param(calf_info, specs.varargs, NO_DEFAULT, 'var')
        return calf_info

    def create_arg_parser(self, calf_info: 'CalfInfo',
                          prog: typing.Optional[str] = None) -> None:
        """Create the parser in the calf info structure

        The parser documents the whole command line, and parses it with
        a blind parser of its own knowing nothing about the
        variable-length parameters, so that their arguments are left for
        the VarArgBroker: see CalfParser.  Subclasses of CalfRunner
        may override this process, e.g., to use their own options.

        Args:

            calf_info: The calf info object
            prog: The program name

        """
        calf_info.parser = CalfParser(
            prog=prog,
            description=calf_info.usage,
            formatter_class=argparse.RawDescriptionHelpFormatter)

    def add_param(self, calf_info: 'CalfInfo', param: str,
                  default: typing.Any, kind: str) -> None:
        """Add a parameter to the parser in the calf info structure

        Args:

            calf_info: The calf info object
            param: The parameter to add
            default: The parameter default value
            kind: The parameter kind, one of 'pos', 'opt', 'var'
                and 'varkw'

        """
        assert calf_info.param_specs
        ptype = calf_info.param_specs.annotations.get(param)
        if not ptype:
            if default is None:
                # None is not a usable type: an unannotated parameter
                # defaulting to None means an optional string, where None
                # tells the function the argument was not given.  Loaders
                # unwrap the parameterized Optional to get str
                ptype = typing.cast(type, typing.Optional[str])
            else:
                ptype = (type(default) if default is not NO_DEFAULT
                         else str)
        info = calf_info.param_info.get(param)
        for selector in self._selectors:
            if selector.match(param, ptype, kind, info):
                loader = selector.make_loader(param, ptype, kind, info,
                                              default)
                loader.fill_by_position = \
                    param in calf_info.positional_params
                calf_info.arg_loaders[param] = loader
                loader.prepare(calf_info)
                return

    def parse_args(self, calf_info: 'CalfInfo', args: ca.Sequence[str]) \
            -> argparse.Namespace:
        """Parse command line arguments

        The parser documents the arguments of the variable-length
        parameters but does not parse them: with one registered, the
        tokens they are made of come back from parse_known_args as the
        remaining arguments for the VarArgBroker: see CalfParser.

        Args:

            calf_info: The calf info object
            args: The command line arguments

        Returns:

            The parsed namespace

        """
        assert calf_info.parser
        if calf_info.var_arg_broker.want_var_arg():
            namespace, others = calf_info.parser.parse_known_args(args)
            # The separator is not a value of its own: it only says that
            # what follows is not an option, and the broker, which never
            # looks for options among the remaining arguments, should not
            # see it as one.  argparse removes it by itself only from the
            # values it hands over to an argument it knows.
            if '--' in others:
                others.remove('--')
        else:
            namespace, others = calf_info.parser.parse_args(args), []
        unrecognized = calf_info.var_arg_broker.distribute(namespace,
                                                           others)
        if unrecognized:
            # report through the parser so the message reads like
            # argparse's own, for the tokens no parameter claimed
            calf_info.parser.error(
                f'unrecognized arguments: {" ".join(unrecognized)}')
        return namespace

    def ns2params(self, calf_info: 'CalfInfo',
                  namespace: argparse.Namespace) \
            -> tuple[list[typing.Any], dict[str, typing.Any]]:
        """Construct parameter from namespace

        The conversion information is used to convert namespace
        produced from argument parser to parameters suitable for
        calling the function used in creating the parser.

        Args:

            calf_info: The calf info object
            namespace: The parsed namespace

        Returns:

            The positional and keyword arguments for calling the function

        """
        pos: list[typing.Any] = []
        kwd: dict[str, typing.Any] = {}
        for loader in calf_info.arg_loaders.values():
            loader.load(namespace, pos, kwd)
        return pos, kwd


class LoaderSelector:
    "Recognize parameters to create argument loaders"
    def match(self, param: str, ptype: type, kind: str,
              info: typing.Optional[ParamInfo]) -> bool:
        """Return whether a parameter is recognized

        Args:

            param: Name of the parameter
            ptype: The parameter type
            kind: One of 'pos', 'opt', 'var' and 'varkw'

        """
        return True

    def select_loader_cls(self, param: str, ptype: type, kind: str,
                          info: typing.Optional[ParamInfo],
                          default: typing.Any) \
            -> type['BaseArgLoader']:
        """Select the loader class to use

        A bool parameter becomes an option only if it defaults to False,
        which makes it a default-off flag.  Otherwise it keeps its own
        place, taking a "0" or "1" value.  Whether the parameter can be
        given by name is no concern of the loader class: CalfRunner marks
        those loaders fill_by_position.

        Args:

            param: Name of the parameter
            ptype: The parameter type
            info: The parameter information parsed from docstring
            kind: One of 'pos', 'opt', 'var' and 'varkw'
            default: The parameter default value

        """
        ptype, default = unwrap_optional(ptype, default)
        if kind == 'opt' or (kind == 'pos' and ptype is bool
                             and default is False):
            return OptArgLoader
        if kind == 'var':
            return VarArgLoader
        if kind == 'varkw':
            return MapArgLoader
        return PosArgLoader

    def make_loader(self, param: str, ptype: type, kind: str,
                    info: typing.Optional[ParamInfo],
                    default: typing.Any) -> 'BaseArgLoader':
        """Create parameter loader for a parameter

        Args:

            param: Name of the parameter
            ptype: The parameter type
            info: The parameter information parsed from docstring
            kind: One of 'pos', 'opt', 'var' and 'varkw'
            default: The parameter default value

        """
        return self.select_loader_cls(param, ptype, kind, info, default)(
            param, ptype, info, default)


class BaseArgLoader:
    """Base class for parameter handling

    A loader gives the value it loads to the target function by name, so
    that a parameter taken as an option in front of this one does not
    shift it.  CalfRunner sets fill_by_position for the parameters which
    cannot be given that way: the positional-only ones, and every one in
    front of a var-arg parameter.

    Args:

        param: The parameter name
        ptype: The parameter type
        info: The parameter information parsed from docstring
        default: The parameter default, or NO_DEFAULT

    """
    def __init__(self, param: str, ptype: type,
                 info: typing.Optional[ParamInfo],
                 default: typing.Any) -> None:
        self._param = param
        self._ptype, self._default = unwrap_optional(ptype, default)
        self._info = info
        self.fill_by_position = False

    def prepare(self, calf_info: 'CalfInfo') -> None:
        """Populate the parser

        Args:

            calf_info: The calf info object

        """
        raise NotImplementedError()

    def basic_arg_extra(self) -> dict[str, typing.Any]:
        "Get basic argument extra parameters"
        extra: dict[str, typing.Any] = {}
        if self._default is not NO_DEFAULT:
            extra['default'] = self._default
        if self._info:
            extra['help'] = self._info.desc
            if self._info.choices:
                extra['choices'] = self._info.choices
        if self._ptype is not str:
            extra['help'] \
                = f'{extra.get("help", "")} [{_gettype(self._ptype)}]'
        return extra

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any], kwd: dict[str, typing.Any]) -> None:
        """Populate parameters for calling the target function

        Args:

            namespace: Where to find the parsed argument
            pos: Positional argument for calling the target function
            kwd: Keyword argument for calling the target function

        """
        raise NotImplementedError()

    def pass_value(self, value: typing.Any, pos: list[typing.Any],
                   kwd: dict[str, typing.Any]) -> None:
        """Pass a parameter value to the target function

        Args:

            value: The value loaded for this parameter
            pos: Positional argument for calling the target function
            kwd: Keyword argument for calling the target function

        """
        if self.fill_by_position:
            pos.append(value)
        else:
            kwd[self._param] = value

    def conv(self, val: typing.Any) -> typing.Any:
        """Perform value conversion

        Args:

            val: The value to convert

        """
        try:
            ptype = _gettype(self._ptype)
            return val if val is None or isinstance(val, self._ptype) else \
                CONVERTERS.get(ptype, typing.cast(ConverterType, ptype))(val)
        except ValueError:
            print(f'Error: Value "{val}" cannot be converted to type'
                  f' {self._ptype.__name__}', file=sys.stderr)
            sys.exit(1)


class PosArgLoader(BaseArgLoader):
    """Define how to handle a positional parameter

    Args:

        param: The parameter name
        ptype: The parameter type
        info: The parameter information parsed from docstring
        default: The parameter default, or NO_DEFAULT

    """

    def prepare(self, calf_info: 'CalfInfo') -> None:
        names = [self._param]
        extra = self.basic_arg_extra()
        if 'default' in extra:
            extra['nargs'] = '?'
        assert calf_info.parser
        calf_info.parser.add_argument(*names, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any], kwd: dict[str, typing.Any]) -> None:
        self.pass_value(self.conv(getattr(namespace, self._param)),
                        pos, kwd)


def _gettype(ptype: type[typing.Any]) -> type[typing.Any]:
    if type(ptype).__name__ != 'UnionType':
        return ptype
    return getinnertype(ptype, ptype.__args__)  # pragma: no cover


def getinnertype(
        ptype: type[typing.Any], ptypes: list[type[typing.Any]]
) -> type[typing.Any]:
    found: list[type[typing.Any]] = []
    for parg in ptypes:
        if parg is not type(None):
            found.append(parg)
    if len(found) != 1:
        raise RuntimeError(f'calf: Type {ptype} not supported')
    return found[0]


class OptArgLoader(BaseArgLoader):
    """Define how to handle an option

    A bool option defaulting to False becomes a flag: it takes no value
    and stores True when specified.  Any other bool option takes a "0" or
    "1" value.

    """

    def prepare(self, calf_info: 'CalfInfo') -> None:
        names = ['--' + self._param]
        if self._info and self._info.short:
            names.insert(0, self._info.short)
        extra = self.basic_arg_extra()
        if self._ptype is bool and self._default is False:
            extra = {'default': False, 'action': 'store_true'}
            if self._info:
                extra['help'] = self._info.desc
        else:
            if 'default' in extra:
                extra['metavar'] \
                    = self._default if self._default != '' else '""'
            else:
                extra['required'] = True
        assert calf_info.parser
        calf_info.parser.add_argument(*names, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any], kwd: dict[str, typing.Any]) -> None:
        self.pass_value(self.conv(getattr(namespace, self._param)),
                        pos, kwd)


class VarArgLoader(BaseArgLoader):
    "Define how to handle a basic remaining option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        extra: dict[str, typing.Any] = {'nargs': '*'}
        if self._info:
            extra['help'] = self._info.desc
        calf_info.var_arg_broker.register_var('', self._param)
        assert calf_info.parser
        calf_info.parser.add_argument(self._param, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any], kwd: dict[str, typing.Any]) -> None:
        pos.extend(self.conv(val)
                   for val in getattr(namespace, self._param))


class MapArgLoader(BaseArgLoader):
    "Define how to handle a map-like remaining option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        extra: dict[str, typing.Any] = {'nargs': '*', 'metavar': 'key=val'}
        if self._info:
            extra['help'] = self._info.desc
        calf_info.var_arg_broker.register_var(
            re.compile(r'^[^=].*='), self._param)
        assert calf_info.parser
        calf_info.parser.add_argument(self._param, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any], kwd: dict[str, typing.Any]) -> None:
        for pval in getattr(namespace, self._param):
            key, _, mval = pval.partition('=')
            kwd[key] = self.conv(mval)


class CompositeArgLoader(BaseArgLoader):
    """Handle a parameter populated from several command line arguments

    Args:

        param: The parameter name
        ptype: The parameter type
        info: The parameter information parsed from docstring
        default: The parameter default, or NO_DEFAULT
        ctor: Callable creating the parameter out of the loaded values
        subloaders: Loaders providing the values for ctor

    """

    def __init__(self, param: str, ptype: type,
                 info: typing.Optional[ParamInfo],
                 default: typing.Any,
                 ctor: FuncType,
                 subloaders: list[BaseArgLoader]) -> None:
        super().__init__(param, ptype, info, default)
        self._ctor = ctor
        self._subloaders = subloaders

    def prepare(self, calf_info: 'CalfInfo') -> None:
        for loader in self._subloaders:
            loader.prepare(calf_info)

    def load(self, namespace: argparse.Namespace,
             pos: list[typing.Any],
             kwd: dict[str, typing.Any]) -> None:
        vararg: list[typing.Any] = []
        varkw: dict[str, typing.Any] = {}
        for loader in self._subloaders:
            loader.load(namespace, vararg, varkw)
        self.pass_value(self._ctor(*vararg, **varkw), pos, kwd)


VarIdentType = typing.Union[str, re.Pattern[str]]
BrokerTupleType = tuple[VarIdentType, str]


class VarArgBroker:
    "Configure how remaining arguments are distributed among namespace"
    def __init__(self) -> None:
        self._registered: list[BrokerTupleType] = []

    def register_var(self, var_ident: VarIdentType, param: str) -> None:
        """Register a request to remaining argument

        Args:

            var_ident: Either a substring to accept a parameter, or a
                regex that must be matched for acceptance

            param: The parameter to assign the remaining argument to

        """
        self._registered.append((var_ident, param))

    def want_var_arg(self) -> bool:
        "Return whether any remaining argument is registered"
        return bool(self._registered)

    @staticmethod
    def _match_arg(var_ident: VarIdentType, pval: str) -> bool:
        if isinstance(var_ident, str):
            return var_ident in pval
        return bool(var_ident.match(pval))

    def distribute(self, namespace: argparse.Namespace,
                   others: list[str]) -> list[str]:
        """Distribute variable length arguments among namespace records

        The blind parser leaves the arguments of the variable-length
        parameters unparsed, so each of them is given to the registered
        parameter accepting it, and the records of all the registered
        parameters are created, whether they take an argument or not.

        Args:

            namespace: Where to record the arguments of the parameters
              which take them

            others: The other arguments not already in namespace that
              also contains remaining arguments

        Returns:

            The arguments that no registered parameter claims

        """
        if not self._registered:
            return []
        for _, param in self._registered:
            setattr(namespace, param, [])
        unrecognized: list[str] = []
        for remain in others:
            for var_ident, param in self._registered:
                if self._match_arg(var_ident, remain):
                    getattr(namespace, param).append(remain)
                    break
            else:
                unrecognized.append(remain)
        return unrecognized


class CalfInfo:
    "Conversion information"
    def __init__(self) -> None:
        self.usage = ''
        self.param_specs: typing.Optional[inspect.FullArgSpec] = None
        # Parameters whose value has to fill a positional slot when
        # calling the function, in the order of the signature
        self.positional_params: list[str] = []
        self.param_info: dict[str, ParamInfo] = {}
        # Iterated in insertion order: the order parameters are declared
        self.arg_loaders: dict[str, BaseArgLoader] = {}
        self.var_arg_broker = VarArgBroker()
        # The one parser of calf: see CalfParser
        self.parser: typing.Optional[CalfParser] = None
        self.namespace: typing.Optional[argparse.Namespace] = None


def call(func: ca.Callable[..., typing.Any],
         args: typing.Optional[ca.Sequence[str]] = None,
         prog: typing.Optional[str] = None,
         doc_parser: DocParserType = google_doc_parser,
         param_parser: ParamParserType = basic_param_parser) -> typing.Any:
    """Call function using Google doc style with basic parameter recognition

    Args:
        func: The function to call
        args: The command line arguments, use sys.argv[1:] if None
        prog: Name of the program
        doc_parser: The doc parser to use
        param_parser: The parameter parser to use

    """
    return CalfRunner(
        [], doc_parser=doc_parser, param_parser=param_parser)(func, args, prog)
