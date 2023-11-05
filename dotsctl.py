#!/usr/bin/env python3
"""Manage dots files collections
"""
#
# :dotsctl:
#   destdir: ~/bin/
#   dpkg:
#     - python3-yaml
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
    return metadata


def log(args, action, filename):
    """Make a log output"""

    if args.verbose:
        print(f"{action} {filename}")


def install_mkdir(args, mkdir):
    """Create one or more directories"""

    if isinstance(mkdir, list):
        for i in mkdir:
            install_mkdir(args, i)

    if not isinstance(mkdir, str):
        raise NotImplementedError("Bad mkdirs metadata")

    path = os.path.expanduser(mkdir)
    if os.path.isdir(path):
        return

    log(args, "MKDIR", path)
    os.makedirs(path, exist_ok=True)
    return


def install_symlink(args, target, linkpath, destdir):
    """Install the dotfile as a symlink"""
    install_mkdir(args, destdir)

    try:
        stat = os.lstat(linkpath)
    except FileNotFoundError:
        stat = None

    # TOCTOU race condition!

    if stat:
        if os.path.stat.S_ISREG(stat.st_mode):
            print(f"Error: will not overwrite regular file {linkpath}")
            return
        if os.path.stat.S_ISLNK(stat.st_mode):
            orig_target = os.readlink(linkpath)
            if orig_target == target:
                # dont report making changes if there are none
                return
        else:
            # Dont know how to handle the type we are trying to overwrite
            raise NotImplementedError("Unknown existing file type")

        os.unlink(linkpath)

    log(args, "SYMLINK", linkpath)
    os.symlink(target, linkpath)


def install_one(args, filename, metadata):
    """Find and process install instructions for one file"""

    # TODO:
    # optionally check required packages

    if "mkdir" in metadata:
        install_mkdir(args, metadata['mkdir'])

    if "destdir" in metadata:
        # The destionation is calculated from a dir name
        metadata["dest"] = os.path.join(
            metadata["destdir"],
            os.path.basename(filename)
        )

    if "dest" in metadata:
        dest = os.path.expanduser(metadata["dest"])
        root, ext = os.path.splitext(dest)

        # TODO:
        # if find libraries is not disabled in metadata
        # and if ext is .py
        # introspect filename for non-packaged libs and install them too

        strip_extension = metadata.get("strip_extension", True)
        if strip_extension:
            dest = root

        destdir = os.path.dirname(dest)
        src_abs = os.path.abspath(filename)
        src_rel = os.path.relpath(src_abs, destdir)

        # TODO:
        # copy to dest:  install_copy()
        # copy to archive:  install_toarchivedir()

        install_symlink(args, src_rel, dest, destdir)


def sources_foreach(args, func):
    conffile = "sources.yml"  # FIXME dry

    result = []
    sources = {}
    if args.pathname:
        for n in args.pathname:
            sources[n] = True
    else:
        sources = _config_load(conffile)

    for source in sources:
        if os.path.isfile(source):
            metadata = _source_load(source)
            if metadata is not None:
                result.append(func(args, source, metadata))
            continue

        files = glob.glob(f"{source}/**", recursive=True, include_hidden=True)
        for file in files:
            if os.path.isfile(file):
                metadata = _source_load(file)
                if metadata is not None:
                    result.append(func(args, file, metadata))
    return result


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
    sources_foreach(args, install_one)


@CLI("debug_meta", arg="pathname")
def subc_debug_meta(args):
    """Dump the discovered metadata"""
    def debug_meta(args, filename, metadata):
        """Pretty print the metadata loaded from the file"""
        db = {filename: metadata}
        print(yaml.safe_dump(db, default_flow_style=False))

    sources_foreach(args, debug_meta)


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

    for name, data in sorted(subc_list.items()):
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
        raise NotImplementedError("No default subcommand")
        # TODO: default

    result = args.func(args)
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
