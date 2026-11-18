# calf: Command Argument Loading Function for Python

Calf lets you remove all your command argument parsing code, at least
for simple cases.  Only the implementation function is left, with
initialization code that uses calf to call this function.  The command
argument parser is configured with a proper docstring, and perhaps
some annotations (argument type) and default values for the
parameters.  In other words, stuffs that you would write anyway.

The docstring can be written in Google, Sphinx, epydoc or Numpy style,
and the design is that it is easy to swap the parsing function with
yours.  In fact, you can customize such a wide range of
characteristics of calf, that you can treat it as a slightly
restricted frontend to the ArgumentParser under the hood.  Used in
this way, you can treat calf as a cute way to configure argparse.

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

The first thing to notice is that the program uses Google docstring
style.  If you want to use another style, just add
`doc_parser=<parser>` to `calf.call`.  Here `<parser>` may be
`calf.google_doc_parser`, `calf.sphinx_doc_parser` (for Sphinx or
Epydoc) or `calf.numpy_doc_parser`.  You can run this program with:

    hello.py Isaac

Here `name` is a positional command line argument: a normal function
argument always maps to a positional command line argument.  If you
want an option instead, you can replace the function argument like
this:

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
to a function.  In this version we are explicit about the type of the
argument.  Note also that the leading `-n` in the docstring describing
the argument, enclosed in parentheses, becomes the short option name.

It is usually a good idea to allow options not to be specified, by
providing a default value.  Positional arguments can also be provided
a default value, but it doesn't mix well with variable arguments
described below.

It is also possible to specify a default which provides no value (so
the program knows that no value is provide).  This is done by either
using a default value of None, or setting in parameter a type of a
parameterized Typing.Optional (without setting a default).  In this
case the normal construction of the target type will not happen.  Such
a parameter without an annotation is an optional string: the function
gets the string given on the command line, or None when the argument
is absent.

There is a special case for booleans.  A boolean parameter defaulting to
False becomes a default-off flag: it takes no command line value, and is
True when specified.  Any other boolean parameter is not treated
specially: it keeps its place as a positional argument, or as an option
for a keyword-only parameter, and takes a command line value of "0"
(false) or "1" (true).  So one defaulting to None is an optional boolean
which stays None when the argument is absent, and one defaulting to True
can still be given "0".  I cannot find a natural way to have a
default-on flag, so it is not provided.  (Let me know if you think
otherwise!)

Variable arguments and keyword arguments can also be used.  Variable
arguments will become a list of the specified type:

    def do_sum(*arg: int) -> None:
        """Sum numbers"""
        print('Sum =', sum(arg, 0))

Here the argument type is "int".  The string passed in the command
line argument will be converted to this type, and in the help message
there will be a little hint (looking like "[int]") indicating the
needed type.  Also note that in this example I don't add documentation
for the arguments: the docstring information is optional, without them
there is no help string but everything else still works.

Keyword arguments cause command line arguments like "<name>=<value>"
to be stolen from the var-arg and form a map.  A type can still be
provided.  For example, if you have:

    import urllib.parse
    def get_query_str(url, **item) -> None:
        "Create URL with parameters"
        qstr = urllib.parse.urlencode(item)
        if qstr:
            url += '?' + qstr
        print(url)

Then you can run something like

    get_query_str.py http://a/b x=a=c y=/

to get `http://a/b?y=%2F&x=a%3Dc`.

Finally, if you're tired of writing initialization code, you have an
additional option to directly place your module under your
PYTHONPATH.  Then you can run your program simply like

    calf hello.hello -n Isaac

## Advanced capability

You can have your function to accept other types.  Calf normally uses
one positional argument or option for each function argument, and
whatever string you specified in the argument will be passed to the
type you specified (via default argument or annotation) as
constructor.  A parameter without an annotation takes its type from
its default value; one with no default at all is a string, and one
defaulting to None is an optional string, so the command line string
reaches your function unchanged.  In cases that passing the string to
the type constructor doesn't do the right thing (e.g., `datetime`),
you can create your own conversion function and add it to
calf.CONVERTERS.  This has been done for `bool` (reading "0" or "1"),
`datetime.date`, `datetime.time` and `datetime.datetime`, and you can
change how they behave by modifying `calf.CONVERTERS` (see the
`nextday.py` example in the docs directory).

But you can also extend calf by creating a subclass of "selector" which
selects function arguments based on name and type.  It then specifies
how to create a "loader" to handle the function argument, which may
use multiple command line arguments (or do any other interaction with
the ArgumentParser).  See `composite.py` in the docs directory to see
how this is done, for the common case.

Calf gives the loaded values to your function by name, so a parameter
which becomes an option does not shift the parameters behind it.  A
parameter before a `/` marker in the signature cannot be given by name,
so its value fills a positional slot, as do all the parameters in front
of a variable-argument one.

Other parts of the module can also be overridden.  For example, you
can change the docstring parser and parameter doc parser.  See the
design document in the docs directory to understand the design and do
all sorts of things with calf.
