#!/usr/bin/env python3
"""Manage dots files collections
"""
#
# :dotsctl:
# destdir: ~/bin/
# dpkg:
#   - python3-yaml
# strip_extension: true
# ...


import argparse
import glob
import io
import os
import yaml


def _config_home():
    """Calculate our config_home"""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if not xdg_config_home:
        xdg_config_home = os.path.expanduser("~/.config")
    return os.path.join(xdg_config_home, "dots")


def _config_load(name):
    """Load a config file from our config_home, or return an empty dict"""
    confdir = _config_home()
    try:
        f = open(os.path.join(confdir, name))
        return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def _config_save(name, config):
    """Save the config file to our config_home"""
    confdir = _config_home()
    os.makedirs(confdir, exist_ok=True)
    f = open(os.path.join(confdir, name), "w")
    print("# Automatically written file, edit with care", file=f)
    yaml.safe_dump(
        config,
        stream=f,
        explicit_start=True,
        explicit_end=True,
        default_flow_style=False,
    )


def _source_load(filename):
    """Open a file and look for dotsctl metadata"""
    check_lines = 30  # basically one page

    fh = open(filename)
    line_nr = 0
    indent = None

    # Look for a metadata header line
    # (and record its indent level)
    while line_nr < check_lines:
        line_nr += 1

        try:
            line = fh.readline()
        except UnicodeDecodeError:
            # Its not text..
            return

        try:
            indent = line.index(":dotsctl:")
            break
        except ValueError:
            continue

    if indent is None:
        # never found a header
        return None

    lines = []
    while True:
        line = fh.readline()[indent:].strip()
        lines.append(line)
        if line == "...":
            break

    metadata = yaml.safe_load(io.StringIO("\n".join(lines)))

    # TODO: DIG HERE
    print("D1", filename)
    print("D2", metadata)


subc_list = {}


def CLI(action, **kwargs):
    def wrap(f):
        entry = {
            "func": f,
            "help": f.__doc__,
        }
        entry.update(kwargs)

        if action in subc_list:
            raise ValueError(f"Duplicate action {action}")
        subc_list[action] = entry
        return f
    return wrap


@CLI("add", arg="pathname")
def subc_add(args):
    """Add a new file or directory to the list of managed sources"""
    conffile = "sources.yml"  # FIXME dry

    sources = _config_load(conffile)
    for name in args.pathname:
        name = os.path.expanduser(name)
        name = os.path.realpath(name)
        if not os.path.exists(name):
            raise ValueError(f"{name} does not exist")
        sources[name] = True
    _config_save(conffile, sources)


@CLI("install", arg="pathname")
def subc_install(args):
    """Install all managed sources or optionally specify just one adhoc file"""
    conffile = "sources.yml"  # FIXME dry

    sources = {}
    if args.pathname:
        for n in args.pathname:
            sources[n] = True
    else:
        sources = _config_load(conffile)

    for source in sources:
        if os.path.isfile(source):
            metadata = _source_load(source)
            # TODO: implement
            continue

        files = glob.glob(f"{source}/**", recursive=True)
        for file in files:
            if os.path.isfile(file):
                metadata = _source_load(file)
                # TODO: implement


def argparser():
    args = argparse.ArgumentParser(
        description=globals()["__doc__"],
    )

    args.add_argument(
        "-v", "--verbose",
        action='store_true', default=False,
        help="Set verbose output",
    )
    # quiet?
    # dry run
    # dest dir

    subc = args.add_subparsers(
        dest="command",
        help="Command",
    )

    for name, data in subc_list.items():
        func = data["func"]
        arg = False
        if "arg" in data and data["arg"]:
            arg = data["arg"]

        cmd = subc.add_parser(name, help=data["help"])
        cmd.set_defaults(func=func)
        if arg:
            cmd.add_argument(arg, nargs="*")

    r = args.parse_args()
    return r


def main():
    args = argparser()

    if not args.command:
        raise NotImplementedError
        # TODO: default

    result = args.func(args)
    print(result)


if __name__ == "__main__":
    main()
