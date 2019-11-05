import argparse
import collections
import typing

import pytest

import calf


def func0a() -> str:
    return 'hello'


def test_degenerated_a():
    assert calf.call(func0a, []), 'hello'


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
        -> typing.Tuple[int, bool, str]:
    """Test function

    Args:
        var1: Variable 1
        var2: (-f) Variable 2
        var3: (-x) Variable 3
        var4: (-v) Variable 4 {foo, bar, baz}

    """
    return var1, var2, var3, var4


def test_help(capsys):
    with pytest.raises(SystemExit):
        calf.call(func1, ['-h'])
    captured = capsys.readouterr()
    assert '\nTest function\n' in captured.out


def test_simple(capsys):
    assert calf.call(func1, ['12', '--var3', 'x']) == (12, False, 'x', 'bar')
    assert calf.call(
        func1, ['12', '-f', '-v', 'foo', '-x', '5']) == (12, True, '5', 'foo')
    with pytest.raises(SystemExit):
        calf.call(func1, ['x', '--var3', 'x'])
    captured = capsys.readouterr()
    assert 'cannot be converted' in captured.err

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


def func3(var1: int, var2: str = 'foo') -> typing.Tuple[int, str]:
    """Test function

    Args:
        var1: Variable 1
        var2: Variable 2

    """
    return var1, var2


def test_pos_default():
    assert calf.call(func3, ['42', 'bar']) == (42, 'bar')
    assert calf.call(func3, ['42']) == (42, 'foo')


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


def test_unimplemented():
    base_loader = calf.BaseArgLoader('p1', str, None, calf.NO_DEFAULT)
    calf_info = calf.CalfInfo()
    with pytest.raises(NotImplementedError):
        base_loader.prepare(calf_info)
    with pytest.raises(NotImplementedError):
        base_loader.load(argparse.Namespace(), [], {})
