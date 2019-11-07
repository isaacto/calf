"Script to serve as a main function if you don't want to write yours"

import importlib
import sys
import typing

import calf


def main(argv: typing.Optional[typing.List[str]] = None) -> None:
    "The main function for your function"
    args = (sys.argv if argv is None else argv)[1:]
    fullname = args.pop(0)
    if fullname in (None, '-h', '--help'):
        print('Usage: calf <module>.<func> ...\n', file=sys.stderr)
        print('Use "calf <module>.<func> -h" for help',
              file=sys.stderr)
        sys.exit(1)
    modname, _, func = fullname.rpartition('.')
    mod = importlib.import_module(modname)
    calf.call(getattr(mod, func), args, prog='calf ' + fullname)


if __name__ == '__main__':  # pragma: no cover
    main()
