#!/usr/bin/env python3

"Show how to define a function with complex params as CLI using calf"

import argparse
import calf
import collections
import typing


# Somehow you have this type...
Name = collections.namedtuple('Name', ['firstname', 'lastname'])


# And you need to support loading this type in your CLI functions...
def hello(name: Name):
    print(name)


# So somewhere in your program you create your own selector
class NameSelector(calf.LoaderSelector):
    def match(self, param: str, ptype: type, kind: str,
              info: typing.Optional[calf.ParamInfo]) -> bool:
        return ptype == Name

    def make_loader(self, param: str, ptype: type, kind: str,
                    info: typing.Optional[calf.ParamInfo],
                    default: typing.Any) -> calf.BaseArgLoader:
        # Here we use a CompositeArgLoader.  Or you may define your own loader.
        return calf.CompositeArgLoader(
            param, ptype, info, default, Name,
            [calf.OptArgLoader('firstname', str,
                               calf.ParamInfo('First name', '-f'), 'Isaac'),
             calf.OptArgLoader('lastname', str,
                               calf.ParamInfo('Last name', '-l'), 'To'),])


# Then define your own "call" function which is use the selector.
def call(func):
    calf.CalfRunner(
        [NameSelector()],
        doc_parser=calf.google_doc_parser,
        param_parser=calf.basic_param_parser)(func)


# Now your CLI is just as usual as you can imagine...
if __name__ == '__main__':
    call(hello)
