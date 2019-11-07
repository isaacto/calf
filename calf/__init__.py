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
import typing


class ParamInfo:
    "Parameter information extracted from doc-strings"
    def __init__(self, desc: str, short: str = '',
                 choices: typing.Optional[typing.List[str]] = None) -> None:
        self.desc = desc
        "The description of the parameter"
        self.short = short
        "The short option string, like '-i'"
        self.choices = choices  # type: typing.Optional[typing.List[str]]
        "The possible choices"


DocParserRetType = typing.Tuple[str, typing.Dict[str, ParamInfo]]
DocParserType = typing.Callable[[str], DocParserRetType]


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
        match = re.match(r'[:@]param\s+([^:]+):\s*(.*)$', ' '.join(group))
        if not match:
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
            param_docs[name] = ParamInfo(' '.join(l.strip() for l in group[1:]))
    return main_doc, param_docs


def indented_groups(inp: str) -> typing.Iterator[typing.List[str]]:
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
    match = re.search('^ *', lines[0])
    assert match
    ilen = len(match.group(0))
    lines = list(itertools.takewhile(lambda x: x[:ilen] == ' ' * ilen, lines))
    is_start = [0 if l[ilen] == ' ' else 1 for l in lines]
    group_cnt = list(itertools.accumulate(is_start))
    for _, group_iter in itertools.groupby(zip(lines, group_cnt),
                                           lambda x: x[1]):
        yield list(x for x, _ in group_iter)


ParamParserType = typing.Callable[[ParamInfo], None]


def basic_param_parser(pinfo: ParamInfo) -> None:
    """Basic parameter calf-specific doc-string parser

    Extract a leading "(-x)" as short option, and trailing "{...,
    ...}" as choices in parameter doc string.  The short option is
    removed from the parameter description as argparse shows it.

    Args:

        pinfo: The parameter information

    """
    match = re.match(r'^\((-[A-Za-z0-9])\)\s*(.*)', pinfo.desc)
    if match:
        pinfo.desc = match.group(2)
        pinfo.short = match.group(1)
    match = re.match(r'^(.*?) *\{([^{}]*)\}([.,;]?)$', pinfo.desc)
    if match and ',' in match.group(2):
        pinfo.choices = [x.strip() for x in re.split(r',\s*', match.group(2))]
        pinfo.desc = match.group(1) + match.group(3)
    pinfo.desc = pinfo.desc.strip()


FuncType = typing.Callable[..., typing.Any]


NO_DEFAULT = object()


class CalfRunner:
    """Convert callables to ArgumentParser and use it to provide a CLI

    Args:

        selectors: The selectors to match parameters and create loaders
        doc_parser: How to parse the docstring
        param_parser: How to parse the parameter string in the docstring

    """
    def __init__(self, selectors: typing.Iterable['LoaderSelector'],
                 doc_parser: DocParserType,
                 param_parser: ParamParserType) -> None:
        self._selectors = list(selectors) + [LoaderSelector()]
        self._doc_parser = doc_parser
        self._param_parser = param_parser

    def __call__(self, func: FuncType,
                 args: typing.Optional[typing.Sequence[str]] = None,
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
        """Create the ArgumentParser in calf_info

        Args:

            calf_info: The calf info object
            prog: The program name

        """
        calf_info.parser = argparse.ArgumentParser(
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

    def parse_args(self, calf_info: 'CalfInfo', args: typing.Sequence[str]) \
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
            namespace, others = calf_info.parser.parse_known_args(args)
        else:
            namespace, others = calf_info.parser.parse_args(args), []
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
        if type(self._ptype) == type(typing.Optional[int]):
            pargs = typing.cast(typing.Optional[typing.Tuple[typing.Any, ...]],
                                getattr(self._ptype, '__args__'))
            if pargs and len(pargs) == 2 and pargs[1] == type(None):
                self._ptype = pargs[0]
                if default is NO_DEFAULT:
                    default = None
        self._info = info
        self._default = default

    def prepare(self, calf_info: 'CalfInfo') -> None:
        """Populate the parser

        Args:

            calf_info: The calf info object

        """
        raise NotImplementedError()

    def basic_arg_extra(self) -> typing.Dict[str, typing.Any]:
        "Get basic argument extra parameters"
        extra = {}  # type: typing.Dict[str, typing.Any]
        if self._default is not NO_DEFAULT:
            extra['default'] = self._default
        if self._info:
            extra['help'] = self._info.desc
            if self._info.choices:
                extra['choices'] = self._info.choices
        if self._ptype is not str:
            extra['help'] = '%s [%s]' % (extra.get('help', ''),
                                         self._ptype.__name__)
        return extra

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

    def conv(self, val: typing.Optional[str]) -> typing.Any:
        """Perform value conversion

        Args:

            val: The value to convert

        """
        try:
            return val if val is None else self._ptype(val)
        except ValueError:
            print('Error: Value "%s" cannot be converted to type %s'
                  % (val, self._ptype.__name__), file=sys.stderr)
            sys.exit(1)


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
        extra = self.basic_arg_extra()
        if 'default' in extra:
            extra['nargs'] = '?'
        assert calf_info.parser
        calf_info.parser.add_argument(*names, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        pos.append(self.conv(getattr(namespace, self._param)))


class OptArgLoader(BaseArgLoader):
    "Define how to handle an option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        names = ['--' + self._param]
        if self._info and self._info.short:
            names.insert(0, self._info.short)
        extra = self.basic_arg_extra()
        if self._ptype == bool:
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
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        kwd[self._param] = self.conv(getattr(namespace, self._param))


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
        pos.extend(self.conv(val)
                   for val in getattr(namespace, self._param))


class MapArgLoader(BaseArgLoader):
    "Define how to handle a map-like remaining option"

    def prepare(self, calf_info: 'CalfInfo') -> None:
        extra = {'nargs': '*',
                 'metavar': 'key=val'}  # type: typing.Dict[str, typing.Any]
        if self._info:
            extra['help'] = self._info.desc
        calf_info.var_arg_broker.register_var(
            re.compile(r'^[^=].*='), self._param)
        assert calf_info.parser
        calf_info.parser.add_argument(self._param, **extra)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        for pval in getattr(namespace, self._param):
            key, _, mval = pval.partition('=')
            kwd[key] = self.conv(mval)


class CompositeArgLoader(BaseArgLoader):
    def __init__(self, param: str, ptype: type,
                 info: typing.Optional[ParamInfo],
                 default: typing.Any,
                 ctor: FuncType,
                 subloaders: typing.List[BaseArgLoader]) -> None:
        super().__init__(param, ptype, info, default)
        self._ctor = ctor
        self._subloaders = subloaders

    def prepare(self, calf_info: 'CalfInfo') -> None:
        for loader in self._subloaders:
            loader.prepare(calf_info)

    def load(self, namespace: argparse.Namespace,
             pos: typing.List[typing.Any],
             kwd: typing.Dict[str, typing.Any]) -> None:
        vararg = []  # type: typing.List[typing.Any]
        varkw = {}  # type: typing.Dict[str, typing.Any]
        for loader in self._subloaders:
            loader.load(namespace, vararg, varkw)
        pos.append(self._ctor(*vararg, **varkw))


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


def call(func: typing.Callable[..., typing.Any],
         args: typing.Optional[typing.Sequence[str]] = None,
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
