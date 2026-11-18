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
to an option.  In this version we are explicit about the type of the
argument.  Note also that the leading `-n` in the docstring describing
the argument, enclosed in parentheses, becomes the short option name.

It is usually a good idea to allow options not to be specified, by
providing a default value.  Positional arguments can also be provided
a default value: the paragraph below on how such an argument settles
also tells you what it does beside variable arguments.

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

Positional arguments are filled in order from the contiguous runs of
command line arguments which are not options.  A parameter takes a
word from a run as long as the run has one; when the run is used up,
the parameters still without a value are settled there, at their
defaults, unless a later parameter which has no default is itself
still short of a word, in which case it and the parameters after it
wait for a later run.  For instance:

    def func(foo: str, bar: bool = False,
             baz: str = 'hello') -> None:
        """Do something

        Args:

            foo: Foo
            bar: (-s) Bar
            baz: Baz

        """

Running `func.py -s d d2` or `func.py d d2 -s` sets foo to 'd', bar to
True and baz to 'd2', but in `func.py d -s d2` the run before the flag
is the single word 'd': it fills the only parameter which needs a
word, so baz is settled there at its default.  The 'd2' behind the
flag has nowhere to go, and the program stops with "unrecognized
arguments: d2".  Give the function a second parameter which has no
default,

    def func(foo: str, qux: str, bar: bool = False,
             baz: str = 'hello') -> None:

and the run before the flag in `func.py 2 -s 3 d` is not enough for
foo and qux together: it fills foo alone, and qux and baz wait for the
next run, which is '3 d', so qux gets '3' and baz gets 'd'.  This is
how argparse matches positional arguments, and as calf is a frontend to
argparse it leaves it that way.  A positional argument whose value may
have to follow an option is better made keyword-only, which turns it
into an option that can be given anywhere: with
`def func(foo: str, bar: bool = False, *, baz: str = 'hello')`,
`func.py d -s --baz d2` sets foo to 'd' and baz to 'd2'.

A parameter which takes a variable number of arguments, `*args` or
`**kwargs` (both below), gets what the settled positional arguments
leave.  With `def func(foo='a', *args)`, `func.py x y` gives foo 'x'
and args ('y',), and `func.py` alone leaves foo at its default with
nothing for args: the first word of a run goes to foo before args sees
any, so nothing reaches args while foo stays at its default.  To have
both, foo has to come after `*args` in the signature, which makes it
keyword-only.  Whether a defaulted parameter settles early or waits
decides what else reaches args: add `*args` to the second example
above, and `func.py 1 -s 2 3` leaves args empty, the run '2 3' being
used up by qux and baz, while `func.py 1 2 -s 3 4` gives args '3' and
'4', baz having been settled at its default by the longer run before
the flag.

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

to get `http://a/b?x=a%3Dc&y=%2F`.

Note that only the arguments left over by the positional parameters are
stolen this way, so give the values of the positional parameters first:
running the program above as `get_query_str.py x=a` sets `url` to `x=a`
and prints it unchanged.  Nor should a pair be named after a parameter
of the function: the pair competes with that parameter for the same
name, and which of them the function sees depends on the rest of the
signature.

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
