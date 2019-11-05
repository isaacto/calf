# calf: Command Argument Loading Function for Python

Calf lets you remove all your command argument parsing code, at least
for simple cases.  Only the implemention function is left, with
initialization code that use calf to call your function.  The command
argument parser is configured with a proper docstring, and perhaps
some annotations (argument type) and default values for the
parameters.  In other words, stuffs that you would write anyway.

The docstring can be written in Google, Sphinx or epydoc style, and
the design is that it is easy to swap the parsing function with yours.
In fact, you can customize a very wide range of characteristics of
calf, that you can treat it as a slightly restricted frontend to the
ArgumentParser under the hood.  Used in this way, you can treat calf
as a cute way to configure argparse.

This package shamelessly stole a lot of ideas from
[plac](https://pypi.org/project/plac/), but hopes to be more focused
on creating comfortable command line interfaces rather than becoming a
Swiss knife for programs with text-only user interface.

## Basic example

Hello-world looks like this:

    def hello(name) -> None:
        """Say hello

        Args:

            name: name of to say hello to

        """
        print('Hello,', name)

    if __name__ == '__main__':
        import calf
        calf.call(hello)

The first thing to note is that the program uses Google docstring
style.  If you want to use another style, just add
`doc_parser=<parser>` to `calf.call`.  Here `<parser>` may be
`calf.google_doc_parser` or `calf.sphinx_doc_parser`.  You can run
this program with:

    hello.py Isaac

Here `name` is a positional command line argument: a normal function
argument always maps to a positional command line argument.  If you
want an option instead, you can replace the function argument with a
keyword-only argument like this:

    def hello(*, name: str = 'Isaac') -> None:
        """Say hello

        Args:

            name: (-n) name of to say hello to

        """
        print('Hello,', name)

Then the program is run like one of the following:

    hello.py
    hello.py --name Cathy
    hello.py -n Cathy

Now `name` is an option: a keyword-only function argument always maps
to a function.  Note also that `-n` in the docstring describing the
argument, leading in parentheses, becomes the short option name.  It
is usually a good idea to allow options not to be specified, by
providing a default value.  Positional arguments can also be provided
a default value, but it doesn't mix with variable arguments as
described below.  In this version we are explicit about the type of
the argument.

There is an exception: any boolean function argument becomes a
default-off flag.  I failed to find a natural way to have a default-on
flag, so it is not provided.

Variable arguments and keyword arguments can also be used.  Variable
arguments will become a list of the specified type:

    def do_sum(*args: int) -> None:
        """Sum numbers"""
        print('Sum =', sum(args, 0))

Keyword arguments causes command line arguments like "<name>=<value>"
to be stolen from the var-arg and form a map.

## Advanced capability

You can have your function accept other types.  Calf would normally
use one positional argument or option for each function argument, and
whatever string you specified in the argument will be passed to the
type you specified (via default argument or annotation) as
constructor.  But you can extend calf by creating a subclass of
"selector" which selects function arguments based on name and type.
It then specifies how to create "loader" to handle the function
argument, and a loader an use multiple command line arguments.  See
`composite.py` in the docs directory to see how this is done.

Other parts of the module can also be overridden.  See the design
document in the docs directory to understand the design and do all
sorts of things with calf.
