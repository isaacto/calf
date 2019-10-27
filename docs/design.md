# Calf Design

## Why another command line parser?!

During my works I came across a Python package called Plac.  I love it
in first sight: what is a better way to create a CLI argument parser
than to just subvert an arbitrary function, perhaps using a little bit
of annotation or decoration?

But after months of using the library, I started to have some strange
feeling on the package.

The first sign of trouble comes when I started to use mypy.  I have to
give up type checking for the main function, using `@no_type_check`.
Fine, I just have a `main()` as stepping stone to the real function.
The `main()` is for Plac, and has no type checking.  Still, one point
taken away from the simplicity of Plac-driven UI.  Instead of writing
my program as a function which Plac knows how to handle, I'm writing a
special function for Plac so that I have a CLI.  This slight
difference takes much of the fun away.

It would be more desirable if Plac just read the type annotation of my
function parameters (I call it parameters here to differentiate it
from command line arguments).  But where to put the additional
information for command options?  Even if Plac and mypy both supports
PEP 593, the result would be uncomfortably verbose.

The real trouble came when I `pylint` the scripts.  Suddenly I
discovered that I have many scripts with very similar, but rather
hairy, annotations.  And there is no way to factor them out.  While it
is easy to write annotations, it is very hard to write a program to
produce functions on-the-fly with the exact parameters and
annotations, just passing to Plac.  It simply doesn't worth the effort.

To be concrete, I have many programs that read an init-style config
file.  I want to manually override some of the options when running
any of these programs, and because I usually want to override a group
of options in the same way, I also put modifications in sections
within the config file which can be "activated".  So each program has
a few "basic" arguments...

    -c <config-file> -s sect1,sect2 sect3__opt3=val3 sect4__opt4=val4 ...

With Plac, I created a few of annotations to support it, which gives
my functions a couple of strings and a dict as parameters.  It is,
though, extremely hard to have those code refactored to remove the
duplication.

The Pythonic way to fix it is, arguably, to make the function take a
Config object as parameter, or perhaps a factory of Config object.
After all, the function really just wants a Config object.  But again,
Plac has no provision for parameters which takes more than one command
line argument to populate.  The quick fix is to create extensible
annotations to allow specifying the Config object or factory.  I did
that, but that doesn't solve the other problems described earlier.

That leaves me wonder: is there something really not Pythonic in the
nice Plac package?  Is it conceptually wrong to use annotations like
the way Plac did?  Then I notice the doc-strings of the Plac-facing
functions is a bit different from others: they won't describe the
parameters.  Perhaps we should just describe the parameters in the doc
strings as in other Python functions, rather than describing them in
annotations that, unfortunately, would normally be monopolized by type
checkers?

After a week of thinking and experiments, the idea of a new package is
born.

## Aim

I want a small package which does the following:

 1. Convert a target function to an argument parser using whatever
    information available, call it using the command line arguments,
    and call the target function accordingly.

 2. The converter is an object, created with parameters configuring
    the converter.  This makes the converter extensible by either
    sub-classing the converter class, or by sub-classing the classes
    of the constructor parameter.

This is quite a bit less than what Plac supports.  E.g., I have no
intention to make calf an interpreter.

## Main concerns

The information of Python functions is geared towards...

 1. The function as a whole (e.g., doc-string), and

 2. The function parameters...

      * Is it positional, keyword, or either?

      * Does it have a default value?  What is it?
      
      * What is the type of the parameters?

Being "Pythonic", we want to reuse these facilities for command line
parsing as well, utilizing argparse.  But while similar, the required
information is not exactly the same:

  * A function parameter may contain very rich information, so it may
    require multiple command line arguments to get the needed
    information for its construction.

  * There is only one list of variable length arguments, but there may
    be multiple parameters needing it.

So there are some mapping required.  To be convenient, this mapping
must be configurable.

## Class list

One can have a quick overview of the design of the module by looking
at the classes it defines.

  * CalfRunner: Main object to convert functions to ArgumentParser and
    call it.
    
  * LoaderSelector: Specifies how to choose argument loaders.  A
    default LoaderSelector is normally used, but special-purpose ones
    may be created and passed to CalfRunner as constructor parameter.

  * ArgLoader: Produced by LoaderSelector to keep information about
    specific parameters, and load the parsed command line arguments to
    give parameter values at the end.  There are many subclasses of
    ArgLoaders, each for handling a different type of parameters.
    There is also a CompositeArgLoader defined so that you can easily
    use multiple ArgLoader for one parameter.

  * VarArgBroker: Determine how variable arguments are to be
    distributed among the Namespace produced by the underlying
    argparse.ArgumentParser.

  * CalfInfo: A POD class storing information during the conversion
    process.  This includes the parsed function doc-string, param
    docs, ArgLoader objects, VarArgBroker, the ArgumentParser, and the
    Namespace resulting from command line parsing.

  * ParamInfo: Information about a parameter extracted from
    doc-string.  Includes its description, short name and allowable
    values.

## The call process

A convenience function "call()" is called, taking the target function
as parameter.  It creates a converter object and call it.  The
converter class then does the following:

  * A CalfInfo object is created.

  * The `apidoc_parser` function is called, to parse the doc-string of
    the target function to a parsed docstring and a list of ParamInfo
    objects.  The simple parser does basic space stripping, while the
    `google_apidoc_parser` would keep only the leading sections and
    parse the "Args" section to ParamInfo.
    
  * The ParamInfo's are parsed using a `param_parser` function,
    finding and possibly stripping away information needed by calf.

  * The ArgumentParser is created with `create_arg_parser`.
    Subclasses may override this process, e.g., to use its own
    options.

  * For each function parameter, a LoaderSelector is selected using
    the `match()` method of all registered selectors.  The selected
    one has the `make_loader()` method called to create the ArgLoader
    object.  The default LoaderSelector uses a few subclasses of
    ArgLoader to handle different kinds of parameters, e.g.,
    positional, optional, etc.

  * The ArgLoader objects have the `prepare` method called to add the
    needed command line argument to the ArgumentParser.  It also
    populate the VarArgBroker by calling `register_var`.

  * The ArgumentParser is used to parse sys.argv, producing a
    Namespace object and some unparsed arguments.  The variable
    argument taken and the unparsed arguments are collected and
    distributed among the Namespace by the VarArgBroker.

  * The resulting Namespace object is used to populate the lists of
    function positional and keyword parameters, by calling the
    `load` method of the ArgLoader objects.

  * The target function with the positional and keyword parameter list
    obtained above.

## `google_apidoc_parser`

The `google_api_parser` provides a little more data than a regular
Google-style docstring:

  * An optional "short option string" created by the leading
    parenthesized short-option string, like "(-o)" if found.

  * An optional "choices" created by the final brace-parenthesized
    list like "{foo, bar}", perhaps followed by a comma, semicolon
    or period.

A function documented fully would look like this:

    def foo(bar: int, *baz: str) -> str:
        """Do foo

        Args:

            bar: (-b) Have a bar

            baz: Do baz, choose from {this, that}.

        Returns:

            A can of worms

        """
