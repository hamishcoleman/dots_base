#!/usr/bin/env python3
"""Manage dots files collections
"""
#
# :dotsctl:
#   destdir: ~/bin/
#   dpkg:
#     - python3-yaml
# ...

# TODO:
# - keep track of installed symlinks, remove the dest if the source is
#   no longer managed
# - Implement tagging to filter installed things

import argparse
import distro
import glob
import io
import os
import yaml


# Hack to support using this on python versions too old to include the
# glob.glob() include_hidden=True option
def _ishidden(pattern):
    return False


glob._ishidden = _ishidden


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
        line = fh.readline()[indent:].rstrip()
        lines.append(line)
        if line == "...":
            break

    metadata = yaml.safe_load(io.StringIO("\n".join(lines)))
    return metadata


class ActionBase:
    def __str__(self):
        raise NotImplementedError()


class ActionSource(ActionBase):
    def __init__(self, filename):
        self.filename = filename

    def __str__(self):
        return f"# source {self.filename}"


class ActionPackage(ActionBase):
    def __init__(self, package):
        self.package = package

    def __str__(self):
        return f"# apt-get -y install {self.package}"


class ActionMkdir(ActionBase):
    def __init__(self, directory):
        self.directory = directory

    def __str__(self):
        return f"mkdir -p {self.directory}"


class ActionSymlink(ActionBase):
    def __init__(self, target, link_name):
        self.target = target
        self.link_name = link_name

    def __str__(self):
        return f"ln -s {self.target} {self.link_name}"


log_verbose = False


def log(action, filename):
    """Make a log output"""
    global log_verbose
    if log_verbose:
        print(f"{action} {filename}")


def install_mkdir(mkdir):
    """Create one or more directories"""
    actions = []

    if isinstance(mkdir, list):
        for i in mkdir:
            actions += install_mkdir(i)
        return actions

    if not isinstance(mkdir, str):
        raise NotImplementedError("Bad mkdirs metadata")

    path = os.path.expanduser(mkdir)
    actions += [ActionMkdir(path)]

    # Skip printing the log message if the path exists
    if os.path.isdir(path):
        return actions
    if os.path.exists(path):
        raise ValueError(f"Path exists and is not a dir: {path}")

    log("MKDIR", path)
    os.makedirs(path, exist_ok=True)
    return actions


def install_symlink_one(target, linkpath):
    """Install the dotfile as a symlink"""
    actions = []
    destdir = os.path.dirname(linkpath)
    actions += install_mkdir(destdir)
    actions += [ActionSymlink(target, linkpath)]

    try:
        stat = os.lstat(linkpath)
    except FileNotFoundError:
        stat = None

    # TOCTOU race condition!

    if stat:
        if os.path.stat.S_ISREG(stat.st_mode):
            print(f"Error: will not overwrite regular file {linkpath}")
            return actions
        if os.path.stat.S_ISLNK(stat.st_mode):
            orig_target = os.readlink(linkpath)
            if orig_target == target:
                # dont report making changes if there are none
                return actions
        else:
            # Dont know how to handle the type we are trying to overwrite
            raise NotImplementedError("Unknown existing file type")

        os.unlink(linkpath)

    log("SYMLINK", linkpath)
    os.symlink(target, linkpath)
    return actions


def install_symlink(data):
    """Create one or more symlinks from a dict of dest: target pairs"""
    actions = []
    for linkpath, target in data.items():
        linkpath = os.path.expanduser(linkpath)
        actions += install_symlink_one(target, linkpath)
    return actions


def install_one(args, filename, metadata):
    """Find and process install instructions for one file"""

    actions = []

    # TODO:
    # optionally check required packages

    if "mkdir" in metadata:
        actions += install_mkdir(metadata['mkdir'])

    if "symlink" in metadata:
        # Install a generic symlink, unrelated to the current filename
        actions += install_symlink(metadata["symlink"])

    if "destdir" in metadata:
        # The destination is calculated from a dir name
        if isinstance(metadata["destdir"], str):
            metadata["destdir"] = [metadata["destdir"]]

        dest = []
        for destdir in metadata["destdir"]:
            dest.append(
                os.path.join(
                    destdir,
                    os.path.basename(filename)
                )
            )
        metadata["dest"] = dest

    if "dotsctl" in metadata:
        basedir = os.path.dirname(filename)
        for this_name, this_meta in sorted(metadata["dotsctl"].items()):
            actions += install_one(
                args,
                os.path.join(basedir, this_name),
                this_meta
            )

    if "dest" in metadata:
        if isinstance(metadata["dest"], str):
            metadata["dest"] = [metadata["dest"]]

        for dest in metadata["dest"]:
            dest = os.path.expanduser(dest)
            root, ext = os.path.splitext(dest)

            # TODO:
            # if find libraries is not disabled in metadata
            # and if ext is .py
            # introspect filename for non-packaged libs and install them too

            strip_extension = False
            if ext in [".py"]:
                strip_extension = True

            strip_extension = metadata.get("strip_extension", strip_extension)
            if strip_extension:
                dest = root

            destdir = os.path.dirname(dest)
            src_abs = os.path.abspath(filename)
            src_rel = os.path.relpath(src_abs, destdir)

            # TODO:
            # copy to dest:  install_copy()
            # copy to archive:  install_toarchivedir()

            actions += install_symlink_one(src_rel, dest)

    return actions


def sources_foreach(args, func):
    conffile = "sources.yml"  # FIXME dry

    data = {}

    def source_append(filename):
        """Trys to add dots data from filename"""
        if filename in data:
            raise ValueError(f"Multiple sources load same ({source})")
        metadata = _source_load(filename)
        if metadata is None:
            return
        data[filename] = metadata

    sources = {}
    if args.pathname:
        for n in args.pathname:
            sources[n] = True
    else:
        sources = _config_load(conffile)

    for source in sources:
        if os.path.isfile(source):
            source_append(source)
            continue

        # With newer python, include_hidden=True
        files = glob.glob(f"{source}/**", recursive=True)
        for file in files:
            if os.path.isfile(file):
                source_append(file)

    result = []
    for source in sorted(data):
        result.append(ActionSource(source))
        f = func(args, source, data[source])
        if f is not None:
            result += (func(args, source, data[source]))
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
    actions = sources_foreach(args, install_one)

    if args.debug:
        for action in actions:
            print(action)


@CLI("debug_meta", arg="pathname")
def subc_debug_meta(args):
    """Dump the discovered metadata"""
    def debug_meta(args, filename, metadata):
        """Pretty print the metadata loaded from the file"""
        db = {filename: metadata}
        print(yaml.safe_dump(db, default_flow_style=False))

    sources_foreach(args, debug_meta)


@CLI("packages_list", arg="pathname")
def subc_packages_list(args):
    """Show the list of package names needed"""
    if distro.id() == 'debian':
        packages_key = "dpkg"
    elif distro.id() == 'raspbian':
        # Gah, this is much annoyance
        packages_key = "dpkg"
    else:
        raise NotImplementedError("Unknown distro")

    def packages(args, filename, metadata):
        if packages_key not in metadata:
            return None
        packages = metadata[packages_key]
        if packages is None:
            return None

        actions = []
        for package in packages:
            actions.append(ActionPackage(package))

        return actions

    raw = sources_foreach(args, packages)
    result = set()

    for i in raw:
        if i is None:
            continue
        if isinstance(i, ActionPackage):
            result.add(i.package)

    for i in sorted(result):
        print(i)


def argparser():
    args = argparse.ArgumentParser(
        description=globals()["__doc__"],
    )

    args.add_argument(
        "--debug",
        action='store_true', default=False,
        help="Set debug output",
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
    if args.verbose:
        global log_verbose
        log_verbose = True

    if not args.command:
        raise NotImplementedError("No default subcommand")
        # TODO: default

    result = args.func(args)
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
