"""Calf: Command Argument Loading Functions

Allow functions to be written naturally while capable of loading
parameters from command line arguments.

"""

# N.B.: To avoid having to say a mouthful of words like "function
# argument" and "command line argument", they are called simply
# "params" and "args" respectively here.

import argparse
import collections
import inspect
import itertools
import re
import sys
import textwrap
import typing


class ParamInfo:
    "Parameter information extracted from doc-strings"
    def __init__(self, desc) -> None:
        self.desc = desc
        "The description of the parameter"
        self.short = ''
        "The short option string, like '-i'"
        self.choices = None  # type: typing.Optional[typing.List[str]]
        "The possible choices"


DocParserRetType = typing.Tuple[str, typing.Dict[str, ParamInfo]]
DocParserType = typing.Callable[[str], DocParserRetType]


def plain_apidoc_parser(apidoc: str) -> DocParserRetType:
    """A doc parser which simply strip spaces

    Args:

        apidoc: The function doc string

    Returns:

        The parsed doc string and empty parameter list

    """
    head, sep, tail = apidoc.partition('\n')
    return '%s%s%s' % (
        head.strip(), sep, textwrap.dedent(tail).rstrip()
    ), {}


def google_apidoc_parser(apidoc: str) -> DocParserRetType:
    """A doc parser handling Google-style apidoc

    Args:

        apidoc: The function doc string

    Returns:

        The parsed doc string and parsed parameter list

    """
    main_doc, param_docs = plain_apidoc_parser(apidoc)
    # Split main part from other sections
    parts = re.split(r'(^(?:Args?|Returns?|Raises?|Yields?|Examples?|'
                     r'Attributes?):\s*$)',
                     main_doc, 1, re.M)
    if len(parts) <= 1:
        return main_doc, param_docs
    main_doc = parts[0]
    remain = ''.join(parts[1:])
    # Skip before Args section
    parts = re.split(r'^Args?:\s*$', remain, 1, re.M)
    if len(parts) <= 1:
        return main_doc, param_docs
    remain = parts[1]
    remain_lines = [l.expandtabs() for l in parts[1].split('\n')
                    if l.strip()]
    if not remain_lines:
        return main_doc, param_docs
    # Get lines of Args section
    match = re.search('^ *', remain_lines[0])
    assert match
    ilen = len(match.group(0))
    remain_lines = list(itertools.takewhile(lambda x: x[:ilen] == ' ' * ilen,
                                            remain_lines))
    # Find lines containing start of options
    is_start = [0 if l[ilen] == ' ' else 1 for l in remain_lines]
    opt_cnt = list(itertools.accumulate(is_start))
    for _, opt_iter in itertools.groupby(zip(remain_lines, opt_cnt),
                                         lambda x: x[1]):
        # Split name from description of option
        arg = ' '.join(l for l, _ in opt_iter if l)
        name, _sep, desc = arg.partition(':')
        name = re.split(r'[\ \(]', name.strip())[0]
        param_docs[name] = ParamInfo(desc=desc.strip())
    return main_doc, param_docs


ParamParserType = typing.Callable[[ParamInfo], None]


def basic_param_parser(pinfo: ParamInfo) -> None:
    """Basic parameter calf-specific doc-string parser

    Extract a leading "(-x)" as short option, and trailing "{...,
    ...}" as choices in parameter doc string.  The short option is
    removed from the parameter description as argparse shows it.

    """
    match = re.match(r'^\((-[A-Za-z0-9])\)\s*(.*)', pinfo.desc)
    if match:
        pinfo.desc = match.group(2)
        pinfo.short = match.group(1)
    match = re.match(r'.*\{([^{}]*)\}[.,;]?$', pinfo.desc)
    if match and ',' in match.group(1):
        pinfo.choices = re.split(r',\s*', match.group(1))
    pinfo.desc = pinfo.desc.strip()


FuncType = typing.Callable[..., typing.Any]


NO_DEFAULT = object()


class CalfRunner:
    "Convert callables to ArgumentParser and use it to provide a CLI"
    def __init__(self, selectors: typing.Iterable['LoaderSelector'],
                 doc_parser: DocParserType,
                 param_parser: ParamParserType) -> None:
        self._selectors = list(selectors) + [LoaderSelector()]
        self._doc_parser = doc_parser
        self._param_parser = param_parser

    def __call__(self, func: FuncType,
                 args: typing.Optional[typing.Iterable[str]] = None) \
            -> typing.Any:
        """Convert func to a parser, collect arguments and call func

        Args:

            func: The function to convert and call
            args: The command line arguments, use sys.argv if None

        Returns:

            Whatever func returns

        """
        calf_info = self.get_calf(func)
        namespace = self.parse_args(calf_info, args or sys.argv)
        pos, kwd = self.ns2params(calf_info, namespace)
        return func(*pos, **kwd)

    def get_calf(self, func: FuncType) -> 'CalfInfo':
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
        self.create_arg_parser(calf_info)
        specs = calf_info.param_specs = inspect.getfullargspec(func)
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

    def create_arg_parser(self, calf_info: 'CalfInfo') -> None:
        """Create the ArgumentParser in calf_info

        Args:

            calf_info: The calf info object

        """
        calf_info.parser = argparse.ArgumentParser(
            usage=calf_info.usage,
            formatter_class=argparse.RawDescriptionHelpFormatter)

    def add_param(self, calf_info: 'CalfInfo', param: str,
                  default: typing.Any, kind: str) -> None:
        """Add a parameter to the parser in the calf info structure

        Args:

            calf_info: The calf info object
            param: The parameter to add
            default: The parameter default value
            kind: The parameter kind, one of 'pos', 'opt', 'varkw' and 'var'

        """
        assert calf_info.param_specs
        ptype = calf_info.param_specs.annotations.get(param)
        if not ptype:
            ptype = type(default) if default is not NO_DEFAULT else str
        info = calf_info.param_info.get(param)
        for selector in self._selectors:
            if selector.match(param, ptype, kind, info):
                calf_info.arg_loaders[param] = selector.make_loader(
                    param, ptype, kind, info, default)
                calf_info.arg_loaders[param].prepare(calf_info)
                return

    def parse_args(self, calf_info: 'CalfInfo', args: typing.Iterable[str]) \
            -> argparse.Namespace:
        """Parse command line arguments

        Args:

            calf_info: The calf info object
            args: The command line arguments

        Returns:

            The parsed namespace

        """
        assert calf_info.parser
        if calf_info.var_arg_broker.want_var_arg():
            namespace, others = calf_info.parser.parse_known_args()
        else:
            namespace, others = calf_info.parser.parse_args(), []
        calf_info.var_arg_broker.distribute(namespace, others)
        return namespace

    def ns2params(self, calf_info: 'CalfInfo',
                  namespace: argparse.Namespace) \
            -> typing.Tuple[typing.List[typing.Any],
                            typing.Dict[str, typing.Any]]:
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
        pos = []  # type: typing.List[typing.Any]
        kwd = {}  # type: typing.Dict[str, typing.Any]
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
            -> typing.Type['BaseArgLoader']:
        """Select the loader class to use

        Args:

            param: Name of the parameter
            ptype: The parameter type
            info: The parameter information parsed from docstring
            kind: One of 'pos', 'opt', 'var' and 'varkw'
            default: The parameter default value

        """
        if kind == 'opt' or (kind == 'pos' and ptype == bool):
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
        self._ptype = ptype
        self._info = info
        self._default = default

    def prepare(self, calf_info: 'CalfInfo') -> None:
        """Populate the parser

        Args:

            calf_info: The calf info object

        """
        raise NotImplementedError()

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        """Populate parameters for calling the target function

        Args:

            namespace: Where to find the parsed argument
            pos: Positional argument for calling the target function
            kwd: Keyword argument for calling the target function

        """
        raise NotImplementedError()


class PosArgLoader(BaseArgLoader):
    """Define how to handle a positional parameter

    Args:

        param: The parameter name
        ptype: The parameter type
        info: The parameter information parsed from docstring
        kind: The parameter kind, one of 'pos', 'opt', 'var' and 'varkw'
        default: The parameter default, or NO_DEFAULT

    """

    def prepare(self, calf_info: 'CalfInfo') -> None:
        names = [self._param]
        extra = {}  # type: typing.Dict[str, typing.Any]
        if self._default is not NO_DEFAULT:
            extra['default'] = self._default
            extra['nargs'] = '?'
        if self._info:
            extra['help'] = self._info.desc
        assert calf_info.parser
        calf_info.parser.add_argument(*names, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        pos.append(self._ptype(getattr(namespace, self._param)))


class OptArgLoader(BaseArgLoader):
    "Define how to handle an option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        names = ['--' + self._param]
        if self._info and self._info.short:
            names.insert(0, self._info.short)
        extra = {}  # type: typing.Dict[str, typing.Any]
        if self._info:
            extra['help'] = self._info.desc
        if self._ptype == bool:
            extra['default'] = False
            extra['action'] = 'store_true'
        elif self._default != NO_DEFAULT:
            extra['default'] = self._default
            extra['metavar'] \
                = self._default if self._default != '' else '""'
        assert calf_info.parser
        calf_info.parser.add_argument(*names, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        kwd[self._param] = self._ptype(getattr(namespace, self._param))


class VarArgLoader(BaseArgLoader):
    "Define how to handle a basic remaining option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        extra = {'nargs': '*'}  # type: typing.Dict[str, typing.Any]
        if self._info:
            extra['help'] = self._info.desc
        calf_info.var_arg_broker.register_var('', self._param)
        assert calf_info.parser
        calf_info.parser.add_argument(self._param, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        pos.extend(self._ptype(val)
                   for val in getattr(namespace, self._param))


class MapArgLoader(BaseArgLoader):
    "Define how to handle a map-like remaining option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        extra = {}  # type: typing.Dict[str, typing.Any]
        if self._info:
            extra['help'] = self._info.desc
        extra['nargs'] = '*'
        calf_info.var_arg_broker.register_var(
            re.compile(r'^[^=].*='), self._param)
        assert calf_info.parser
        calf_info.parser.add_argument(self._param, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        for pval in getattr(namespace, self._param):
            key, _, mval = pval.partition('=')
            kwd[key] = self._ptype(mval)


VarIdentType = typing.Union[str, typing.Pattern[str]]
BrokerTupleType = typing.Tuple[VarIdentType, str]


class VarArgBroker:
    "Configure how remaining arguments are distributed among namespace"
    def __init__(self) -> None:
        self._registered = []  # type: typing.List[BrokerTupleType]

    def register_var(self, var_ident: VarIdentType, param: str) -> None:
        """Register a request to remaining argument

        Args:

            var_ident: Either a substring to accept a parameter, or a
                regex that must be matched for acceptance

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
                   others: typing.List[str]) -> None:
        """Distribute variable length arguments among namespace records

        Collect the variable length argument, and look for a
        registered parameter accepting the argument for each of them.
        Once found the argument is appended to the parameter record of
        the namespace.

        Args:

            namespace: The namespace to collection arguments and
              assign them to parameters

            others: The other arguments not already in namespace that
              also contains remaining arguments

        """
        if not self._registered:
            return
        remains = getattr(namespace, self._registered[0][1]) + others
        getattr(namespace, self._registered[0][1])[:] = []
        for remain in remains:
            for var_ident, param in self._registered:
                if self._match_arg(var_ident, remain):
                    getattr(namespace, param).append(remain)
                    break
            else:
                raise ValueError('Remaining argument %s not recognized'
                                 % (remain,))


class CalfInfo:
    "Conversion information"
    def __init__(self) -> None:
        self.usage = ''
        self.param_specs = None  # type: typing.Optional[inspect.FullArgSpec]
        self.param_info = {}  # type: typing.Dict[str, ParamInfo]
        self.arg_loaders = collections.OrderedDict(
        )  # type: typing.Dict[str, BaseArgLoader]
        self.var_arg_broker = VarArgBroker()
        self.parser = None  # type: typing.Optional[argparse.ArgumentParser]
        self.namespace = None  # type: typing.Optional[argparse.Namespace]


def call(func: typing.Callable[..., typing.Any]) -> None:
    "Call function using Google apidoc style with basic parameter recognition"
    CalfRunner([], doc_parser=google_apidoc_parser,
               param_parser=basic_param_parser)(func)
