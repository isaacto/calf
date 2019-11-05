#!/usr/bin/env python3

"Show how to define a function with simple params as CLI using calf"

import argparse
import calf
import collections
import typing


GREETING = {
    1: 'Cheers.',
    2: 'Have a nice day.',
    3: 'Nice to meet you.',
}


# Define your function just like other functions, but note the (-s) as
# short option names, and {1, 2, 3} as choices.
def hello(name: str = 'Isaac', *args, style = 2, **kwargs: float) -> None:
    """Say hello

    Args:

        name: name to say hello to

        style: (-s) style, choose among {1, 2, 3}

        args: values

        kwargs: keyword values

    """
    print('Hello,', name)
    print(GREETING[style])
    print(args)
    print(kwargs)


# Your main program just use calf.call to call your CLI function.
if __name__ == '__main__':
    calf.call(hello)
