import argparse
import datetime
import collections
import typing

import pytest

import calf
import calf.__main__ as cm


def func0a() -> str:
    return 'hello'


def test_degenerated_a():
    assert calf.call(func0a, []), 'hello'
    assert calf.call(func0a, [], doc_parser=calf.sphinx_doc_parser), 'hello'
    assert calf.call(func0a, [], doc_parser=calf.numpy_doc_parser), 'hello'


def func0b() -> str:
    """func0b

    Say hello

    Returns:

        Constant value 'hello'

    """
    return 'hello'


def test_degenerated_b(capsys):
    assert calf.call(func0b, []), 'hello'
    with pytest.raises(SystemExit):
        calf.call(func0b, ['-h'])
    captured = capsys.readouterr()
    assert 'Say hello' in captured.out
    assert 'Constant' not in captured.out


def func0c() -> str:
    """func0c

    Args:

    """
    return 'hello'


def test_degenerated_c(capsys):
    assert calf.call(func0c, []), 'hello'
    with pytest.raises(SystemExit):
        calf.call(func0c, ['-h'])
    captured = capsys.readouterr()
    assert 'func0c' in captured.out


def func1(var1: int, var2: bool, *, var3: str, var4: str='bar') \
        -> typing.Tuple[int, bool, str, str]:
    """Test function

    Args:
        var1: Variable 1
        var2: Variable 2
        var3: (-x) Variable 3
        var4: (-v) Variable 4 {foo, bar, baz}

    """
    return var1, var2, var3, var4


def func1s(var1: int, var2: bool, *, var3: str, var4: str='bar') \
        -> typing.Tuple[int, bool, str, str]:
    """Test function

    :param var1: Variable 1
    :param var2: Variable 2
    :param var3: (-x) Variable 3
    :param var4: (-v) Variable 4 {foo, bar, baz}
    :other: other

    """
    return var1, var2, var3, var4


def func1n(var1: int, var2: bool, *, var3: str, var4: str='bar') \
        -> typing.Tuple[int, bool, str, str]:
    """Test function

    Parameter
    ---------
    var1
       Variable 1
    var2 :
       Variable 2
    var3:
       (-x) Variable 3
    var4 : str
       (-v) Variable 4 {foo, bar, baz}

    Returns
    -------

       Nothing

    """
    return var1, var2, var3, var4


def func1d(var1: datetime.date, var2: datetime.time, var3: datetime.datetime) \
        -> typing.Tuple[datetime.date, datetime.time, datetime.datetime]:
    return var1, var2, var3


def test_help(capsys):
    with pytest.raises(SystemExit):
        calf.call(func1, ['-h'])
    captured = capsys.readouterr()
    assert '-x VAR3, --var3' in captured.out
    with pytest.raises(SystemExit):
        calf.call(func1s, ['-h'], doc_parser=calf.sphinx_doc_parser)
    captured = capsys.readouterr()
    assert '-x VAR3, --var3' in captured.out
    with pytest.raises(SystemExit):
        calf.call(func1n, ['-h'], doc_parser=calf.numpy_doc_parser)
    captured = capsys.readouterr()
    assert '-x VAR3, --var3' in captured.out


def test_simple(capsys):
    assert calf.call(
        func1, ['12', '0', '--var3', 'x']) == (12, False, 'x', 'bar')
    assert calf.call(
        func1, ['12', '1', '-v', 'foo', '-x', '5']) == (12, True, '5', 'foo')
    with pytest.raises(SystemExit):
        calf.call(func1, ['x', '0', '--var3', 'x'])
    captured = capsys.readouterr()
    assert 'cannot be converted' in captured.err
    assert calf.call(func1d, ['2020-03-15', '22:30', '2020-03-15T22:30']) \
        == (datetime.date(2020, 3, 15),
            datetime.time(22, 30),
            datetime.datetime(2020, 3, 15, 22, 30))
    assert calf.call(
        func1d, ['2020-03-15', '22:30:15', '2020-03-15T22:30:15']) \
        == (datetime.date(2020, 3, 15),
            datetime.time(22, 30, 15),
            datetime.datetime(2020, 3, 15, 22, 30, 15))


def func8(name: str = 'n', verbose: bool = False) \
        -> typing.Tuple[str, bool]:
    """Test function with a flag

    Args:
        name: (-n) Name
        verbose: (-v) Be verbose

    """
    return name, verbose


def test_bool_flag(capsys):
    # a bool defaulting to False is a default-off flag: it takes no value
    assert calf.call(func8, []) == ('n', False)
    assert calf.call(func8, ['--verbose']) == ('n', True)
    assert calf.call(func8, ['bob', '-v']) == ('bob', True)
    assert calf.call(func8, ['-v', 'bob']) == ('bob', True)
    with pytest.raises(SystemExit):
        calf.call(func8, ['-h'])
    assert '-v, --verbose' in capsys.readouterr().out


def func9(flag: bool, name: str = 'n', *, other: bool = False) \
        -> typing.Tuple[bool, str, bool]:
    """Test function with bool values

    Args:
        flag: Flag, 0 or 1
        name: Name
        other: (-o) Other

    """
    return flag, name, other


def test_bool_value(capsys):
    # a bool without a default takes a "0" or "1" value where it stands;
    # other defaults to False, so it is a flag instead
    assert calf.call(func9, ['1']) == (True, 'n', False)
    assert calf.call(func9, ['0', 'bob', '--other']) \
        == (False, 'bob', True)
    with pytest.raises(SystemExit):
        calf.call(func9, ['2'])
    assert 'cannot be converted' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        calf.call(func9, ['yes'])
    assert 'cannot be converted' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        calf.call(func9, [])
    assert 'required' in capsys.readouterr().err


def func10(pos: typing.Optional[bool] = None, *, other: bool = None) \
        -> typing.Tuple[typing.Optional[bool], typing.Optional[bool]]:
    """Test function with bools defaulting to no value

    Args:
        pos: Positional flag, 0 or 1
        other: (-o) Optional flag, 0 or 1

    """
    return pos, other


def test_bool_no_value_default(capsys):
    # a bool defaulting to None, spelled with None or with a
    # parameterized Optional, is no flag either: it takes a value, and
    # None tells the function the argument was not given
    assert calf.call(func10, []) == (None, None)
    assert calf.call(func10, ['1']) == (True, None)
    assert calf.call(func10, ['0', '--other', '1']) == (False, True)
    with pytest.raises(SystemExit):
        calf.call(func10, ['--other', 'yes'])
    assert 'cannot be converted' in capsys.readouterr().err


def func11(flag: bool = True) -> bool:
    """Test function with a default-on bool

    Args:
        flag: Flag, 0 or 1

    """
    return flag


def test_bool_true_default():
    # a bool defaulting to True takes a value too, so it can say False
    assert calf.call(func11, []) is True
    assert calf.call(func11, ['0']) is False


def func12(*flags: bool, **kw: bool) \
        -> typing.Tuple[typing.Tuple[bool, ...], typing.Dict[str, bool]]:
    """Test function with bool varargs

    Args:
        flags: Flags
        kw: Keyword flags

    """
    return flags, kw


def test_bool_varargs():
    assert calf.call(func12, ['1', '0', 'a=1', 'b=0']) \
        == ((True, False), {'a': True, 'b': False})


def func2(*args, **kwargs: str) -> typing.Tuple[  # type: ignore
        typing.List[str], typing.Dict[str, str]]:
    """Test vararg function

    Args:
        args: Var args
        kwargs: Keyword args

    """
    return args, kwargs


def test_varargs():
    assert calf.call(func2, ['foo', 'bar']) == (('foo', 'bar'), {})
    assert calf.call(func2, ['foo1=bar', 'foo2=baz']) \
        == ((), {'foo1': 'bar', 'foo2': 'baz'})
    assert calf.call(func2, ['foo', 'foo1=bar', 'bar']) \
        == (('foo', 'bar'), {'foo1': 'bar'})


def func3(var1: int, var2: typing.Optional[int],
          var3: str = 'foo') -> typing.Tuple[int, str]:
    """Test function

    Args:
        var1: Variable 1
        var2: Variable 2
        var3: Variable 3

    """
    return var1, var2, var3


def test_pos_default():
    assert calf.call(func3, ['42', '15', 'bar']) == (42, 15, 'bar')
    assert calf.call(func3, ['42']) == (42, None, 'foo')


def func6(var1=None, var2: str = 'foo') -> typing.Tuple[
        typing.Optional[str], str]:
    """Test function with an unannotated None default

    Args:
        var1: Variable 1
        var2: Variable 2

    """
    return var1, var2


def test_unannotated_none_default():
    # an unannotated None default means an optional string, where None
    # tells the function the argument was not given
    assert calf.call(func6, []) == (None, 'foo')
    assert calf.call(func6, ['bar', 'baz']) == ('bar', 'baz')
    with pytest.raises(SystemExit):
        calf.call(func6, ['bar', 'baz', 'extra'])


def func7(*, var1=None, var2: str = 'foo') -> typing.Tuple[
        typing.Optional[str], str]:
    """Test function with an unannotated None default for an option

    Args:
        var1: (-v) Variable 1
        var2: Variable 2

    """
    return var1, var2


def test_unannotated_none_default_option(capsys):
    assert calf.call(func7, []) == (None, 'foo')
    assert calf.call(func7, ['--var1', 'bar']) == ('bar', 'foo')
    assert calf.call(func7, ['-v', 'bar', '--var2', 'baz']) == ('bar', 'baz')
    with pytest.raises(SystemExit):
        calf.call(func7, ['-h'])
    captured = capsys.readouterr()
    assert '-v VAR1, --var1 VAR1' in captured.out
    assert 'NoneType' not in captured.out


def func4(**kwargs: str) -> typing.Dict[str, str]:
    """Test function

    Args:
        kwargs: Kwd

    """
    return kwargs


def test_kwargs_only():
    assert calf.call(func4, ['bar=42']) == {'bar': '42'}
    with pytest.raises(ValueError):
        calf.call(func4, ['bar'])


Name = collections.namedtuple('Name', ['firstname', 'lastname'])


def func5(name: Name):
    return(name)


class NameSelector(calf.LoaderSelector):
    def match(self, param: str, ptype: type, kind: str,
              info: typing.Optional[calf.ParamInfo]) -> bool:
        return ptype == Name

    def make_loader(self, param: str, ptype: type, kind: str,
                    info: typing.Optional[calf.ParamInfo],
                    default: typing.Any) -> calf.BaseArgLoader:
        return calf.CompositeArgLoader(
            param, ptype, info, default, Name,
            [calf.OptArgLoader('firstname', str,
                               calf.ParamInfo('First name', '-f'), 'Isaac'),
             calf.OptArgLoader('lastname', str,
                               calf.ParamInfo('Last name', '-l'), 'To')])


def test_composite():
    assert calf.CalfRunner(
        [NameSelector()],
        doc_parser=calf.google_doc_parser,
        param_parser=calf.basic_param_parser)(func5, []) == Name('Isaac', 'To')


def func13(first: str, second: bool = False,
           third: str = 'hello') -> typing.Tuple[str, bool, str]:
    """Test function with a flag between positional parameters

    Args:
        first: First
        second: (-s) Second
        third: Third

    """
    return first, second, third


def test_flag_between_params():
    # a parameter handled as an option leaves no hole behind: calf gives
    # the values to the function by name
    assert calf.call(func13, ['a']) == ('a', False, 'hello')
    assert calf.call(func13, ['a', 'w']) == ('a', False, 'w')
    assert calf.call(func13, ['-s', 'a']) == ('a', True, 'hello')
    assert calf.call(func13, ['-s', 'a', 'w']) == ('a', True, 'w')


def func14(a: int, b: str, /,
           c: float = 1.5) -> typing.Tuple[int, str, float]:
    """Test function with positional-only parameters

    Args:
        a: A
        b: B
        c: C

    """
    return a, b, c


def test_positional_only():
    assert calf.call(func14, ['1', 'b']) == (1, 'b', 1.5)
    assert calf.call(func14, ['1', 'b', '2.5']) == (1, 'b', 2.5)


def func15(v: bool = False, /) -> bool:
    """Test function with a positional-only bool

    Args:
        v: V

    """
    return v


def test_positional_only_bool(capsys):
    # the bool rule does not depend on the parameter being nameable: the
    # flag value fills the positional slot of the call
    assert calf.call(func15, []) is False
    assert calf.call(func15, ['--v']) is True
    with pytest.raises(SystemExit):
        calf.call(func15, ['1'])
    assert 'unrecognized' in capsys.readouterr().err


def func16(verbose: bool = False,
           *files: str) -> typing.Tuple[bool, typing.Tuple[str, ...]]:
    """Test function with a flag before a var-arg parameter

    Args:
        verbose: (-v) Be verbose
        files: Files

    """
    return verbose, files


def test_flag_before_varargs():
    # the parameters in front of a var-arg one fill the positional slots
    # in order, as a var-arg never takes a keyword
    assert calf.call(func16, []) == (False, ())
    assert calf.call(func16, ['-v', 'a', 'b']) == (True, ('a', 'b'))
    assert calf.call(func16, ['a']) == (False, ('a',))


def func17(name: Name, /, extra: str = 'x') -> typing.Tuple[Name, str]:
    return name, extra


def test_composite_positional_only():
    assert calf.CalfRunner(
        [NameSelector()],
        doc_parser=calf.google_doc_parser,
        param_parser=calf.basic_param_parser)(func17, ['-f', 'A']) \
        == (Name('A', 'To'), 'x')


def func18(first, *args) -> typing.Tuple[str, typing.Tuple[str, ...]]:
    """Test function with a required parameter before the var args

    Args:
        first: First
        args: Var args

    """
    return first, args


def test_calf_parser(capsys):
    # the blind parser behind the calf parser knows no var args, so
    # their arguments come back as the remaining ones, and what it does
    # not parse it does not ask for either; the calf parser documents
    # them
    assert calf.call(func2, ['x', '--', 'y']) == (('x', 'y'), {})
    with pytest.raises(SystemExit):
        calf.call(func2, ['-h'])
    out = capsys.readouterr().out
    assert '[key=val ...]' in out and '[args ...]' in out
    with pytest.raises(SystemExit):
        calf.call(func18, [])
    assert 'required: first\n' in capsys.readouterr().err


def test_unimplemented():
    base_loader = calf.BaseArgLoader('p1', str, None, calf.NO_DEFAULT)
    calf_info = calf.CalfInfo()
    with pytest.raises(NotImplementedError):
        base_loader.prepare(calf_info)
    with pytest.raises(NotImplementedError):
        base_loader.load(argparse.Namespace(), [], {})


def test_getinner():
    with pytest.raises(RuntimeError):
        calf.getinnertype(type(None), [])
    with pytest.raises(RuntimeError):
        calf.getinnertype(type(None), [int, str])
    assert calf.getinnertype(type(None), [int, type(None)]) is int


def test_main():
    cm.main(['test_calf', 'test_calf.func0a'])
    with pytest.raises(SystemExit):
        cm.main(['test_calf', '-h'])
