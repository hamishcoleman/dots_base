#!/usr/bin/env python3
"""Manage dots files collections
"""
#
# :dotsctl:
# dest: ~/bin/dotsctl
# dpkg:
#   - python3-yaml
# ...


import argparse
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


def subc_add(args):
    """Add a new file or directory to the list of managed sources"""
    conffile = "sources.yml"

    sources = _config_load(conffile)
    for name in args.pathname:
        name = os.path.expanduser(name)
        name = os.path.realpath(name)
        if not os.path.exists(name):
            raise ValueError(f"{name} does not exist")
        sources[name] = True
    _config_save(conffile, sources)


def subc_install(args):
    """Install all managed sources or optionally specify just one adhoc file"""
    raise NotImplementedError()


subc_list = {
    "add": {
        "func": subc_add,
        "arg": "pathname",
    },
    "install": {
        "func": subc_install,
        "arg": "pathname",
    },
}


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

        cmd = subc.add_parser(name, help=func.__doc__)
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

