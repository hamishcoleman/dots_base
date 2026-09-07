#!/usr/bin/env python3
"""Manage dots files collections
"""
#
# :dotsctl:
#   destdir: ~/bin/
#   dpkg:
#     - python3-yaml
#     - python3-distro
# ...

# TODO:
# - keep track of installed symlinks, remove the dest if the source is
#   no longer managed
# - Implement tagging to filter installed things

import argparse
import glob
import io
import os
import yaml


# Hack to support using this on python versions too old to include the
# glob.glob() include_hidden=True option
def _ishidden(pattern):
    return False


glob._ishidden = _ishidden


class Config:
    def __init__(self):
        name = "dots"
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if not xdg_config_home:
            xdg_config_home = os.path.expanduser("~/.config")

        self.dir = os.path.join(xdg_config_home, name)
        self.config = {}

    def load(self, name):
        """Try to load a config file from our dir"""

        if self.config:
            raise ValueError("Cannot load config twice")

        try:
            f = open(os.path.join(self.dir, name))
            self.config = yaml.safe_load(f)
        except FileNotFoundError:
            pass

    def save(self, name):
        """Save the config file into our dir"""
        os.makedirs(self.dir, exist_ok=True)
        f = open(os.path.join(self.dir, name), "w")
        print("# Automatically written file, edit with care", file=f)
        yaml.safe_dump(
            self.config,
            stream=f,
            explicit_start=True,
            explicit_end=True,
            default_flow_style=False,
        )


def _source_load(filename):
    """Open a file and look for dotsctl metadata"""
    check_lines = 30  # basically one page

    if os.path.islink(filename):
        # Avoid recursion
        return None

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
        if len(lines) > 100:
            raise ValueError(f"long header or missing end in {filename}")

    metadata = yaml.safe_load(io.StringIO("\n".join(lines)))
    return metadata


class ActionBase:
    def __init__(self):
        self.verbose = False

    def __str__(self):
        raise NotImplementedError()

    def act(self):
        # default to taking no action
        pass

    @classmethod
    def from_metadata(cls, metadata):
        raise NotImplementedError()

    def log(self, filename):
        if self.verbose:
            print(f"{self.name} {filename}")


class ActionSource(ActionBase):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename

    def __str__(self):
        return f"# dotsctl install {self.filename}"


class ActionDpkg(ActionBase):
    def __init__(self, package):
        super().__init__()
        self.package = package

    def __str__(self):
        return f"# sudo apt-get install {self.package}"

    @classmethod
    def from_metadata(cls, metadata):
        if not isinstance(metadata, list):
            metadata = [metadata]

        actions = []
        for package in metadata:
            actions += [cls(package)]

        return actions


class ActionMkdir(ActionBase):
    name = "MKDIR"

    def __init__(self, directory):
        super().__init__()
        self.directory = os.path.expanduser(directory)

    def __str__(self):
        return f"mkdir -p {self.directory}"

    def act(self):
        # Dont take any action if the path already exists
        if os.path.isdir(self.directory):
            return
        if os.path.exists(self.directory):
            raise ValueError(f"Path exists and is not a dir: {self.directory}")
        self.log(self.directory)
        os.makedirs(self.directory, exist_ok=True)

    @classmethod
    def from_metadata(cls, metadata):
        if not isinstance(metadata, list):
            metadata = [metadata]

        actions = []
        for path in metadata:
            actions += [cls(path)]

        return actions


class ActionSymlink(ActionBase):
    name = "SYMLINK"

    def __init__(self, target, link_name):
        super().__init__()
        self.target = target
        self.link_name = os.path.expanduser(link_name)

    def __str__(self):
        return f"ln -s {self.target} {self.link_name}"

    def act(self):
        try:
            stat = os.lstat(self.link_name)
        except FileNotFoundError:
            stat = None

        # TOCTOU race condition!

        if stat:
            if os.path.stat.S_ISREG(stat.st_mode):
                print(f"Error: will not overwrite file {self.link_name}")
                return
            if os.path.stat.S_ISLNK(stat.st_mode):
                orig_target = os.readlink(self.link_name)
                if orig_target == self.target:
                    # dont report making changes if there are none
                    return
            else:
                # Dont know how to handle the type we are trying to overwrite
                raise NotImplementedError("Unknown existing file type")

            os.unlink(self.link_name)

        self.log(self.link_name)
        os.symlink(self.target, self.link_name)

    @classmethod
    def from_metadata(cls, metadata):
        actions = []
        for linkpath, target in metadata.items():
            destdir = os.path.dirname(linkpath)
            actions += [ActionMkdir(destdir)]
            actions += [cls(target, linkpath)]

        return actions


def parse_metadata(args, filename, metadata):
    """Find and process install instructions for one file"""

    actions = []

    # TODO:
    # optionally check required packages

    if "dpkg" in metadata:
        actions += ActionDpkg.from_metadata(metadata['dpkg'])

    if "mkdir" in metadata:
        actions += ActionMkdir.from_metadata(metadata['mkdir'])

    if "symlink" in metadata:
        # Install a generic symlink, unrelated to the current filename
        actions += ActionSymlink.from_metadata(metadata["symlink"])

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
            this_name = os.path.expanduser(this_name)
            if not this_name.startswith("/"):
                this_name = os.path.join(basedir, this_name)

            actions += parse_metadata(
                args,
                this_name,
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

            if args.relpath:
                src_rel = os.path.relpath(src_abs, destdir)
            else:
                src_rel = src_abs

            # TODO:
            # copy to dest:  install_copy()
            # copy to archive:  install_toarchivedir()

            actions += ActionSymlink.from_metadata({dest: src_rel})

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

    c = Config()
    if args.pathname:
        for n in args.pathname:
            c.config[n] = True
    else:
        c.load(conffile)

    for source in c.config:
        if os.path.isfile(source):
            source_append(source)
            continue

        # With newer python, include_hidden=True
        files = glob.glob(f"{source}/**", recursive=True)
        for file in files:
            if os.path.isfile(file):
                source_append(file)

    results = []
    for source in sorted(data):
        results += [ActionSource(source)]

        this_result = (func(args, source, data[source]))
        if this_result is not None:
            results += this_result
    return results


def subc_add(args):
    """Add a new file or directory to the list of managed sources"""
    conffile = "sources.yml"  # FIXME dry

    c = Config()
    c.load(conffile)
    for name in args.pathname:
        name = os.path.expanduser(name)
        name = os.path.realpath(name)
        if not os.path.exists(name):
            raise ValueError(f"{name} does not exist")
        c.config[name] = True
    c.save(conffile)


def subc_install(args):
    """Install all managed sources or optionally specify just one adhoc file"""
    actions = sources_foreach(args, parse_metadata)

    for action in actions:
        if args.verbose:
            action.verbose = True
        if args.debug:
            print(action)
        if not args.dry_run:
            action.act()


def subc_debug_meta(args):
    """Dump the discovered metadata"""
    def debug_meta(args, filename, metadata):
        """Pretty print the metadata loaded from the file"""
        db = {filename: metadata}
        print(yaml.safe_dump(db, default_flow_style=False))

    sources_foreach(args, debug_meta)


def subc_packages_list(args):
    """Show the list of package names needed"""
    try:
        import distro

        distro2key = {
            "debian": "dpkg",
            "ubuntu": "dpkg",
            "raspbian": "dpkg",
            "pop": "dpkg",
        }
        packages_key = distro2key[distro.id()]

    except KeyError:
        raise NotImplementedError("Unknown distro")
    except ModuleNotFoundError:
        # just guess then
        packages_key = "dpkg"

    def packages(args, filename, metadata):
        return metadata.get(packages_key, None)

    raw = sources_foreach(args, packages)
    result = set()

    for i in raw:
        if i is None:
            continue
        if isinstance(i, str):
            result.add(i)

    for i in sorted(result):
        print(i)


def subc_source_list(args):
    """Show the list of source_id values"""

    def source_id(args, filename, metadata):
        return [{filename: metadata.get("source_id", None)}]

    raw = sources_foreach(args, source_id)
    result = {}

    for i in raw:
        if i is None:
            continue
        if isinstance(i, ActionBase):
            continue

        result.update(i)

    for filename, source_id in sorted(result.items()):
        if source_id is None:
            continue
        print(filename, source_id)


def argparser_subc(args, subc_list):
    subc = args.add_subparsers(
        dest="command",
        help="Command",
    )

    for name, data in sorted(subc_list.items()):
        if "func" in data:
            help = data["func"].__doc__
        elif "help" in data:
            help = data["help"]
        else:
            help = None
        cmd = subc.add_parser(name, help=help)

        if "func" in data:
            func = data["func"]
            cmd.set_defaults(func=func)

            arg = False
            if "arg" in data and data["arg"]:
                arg = data["arg"]

            if arg:
                cmd.add_argument(
                    arg,
                    nargs="*",
                    # help
                    # type
                )

        if "subc" in data:
            argparser_subc(cmd, data["subc"])


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
    args.add_argument(
        "-n", "--dry-run",
        action='store_true', default=False,
        help="Make no changes",
    )
    # quiet?
    # dest dir

    subc_list = {
        "add": {
            "func": subc_add,
            "arg": "pathname",
        },
        "debug": {
            "help": "Subcommands for debugging dotsctl metadata",
            "subc": {
                "meta": {
                    "func": subc_debug_meta,
                    "arg": "pathname",
                },
            },
        },
        "install": {
            "func": subc_install,
            "arg": "pathname",
        },
        "package": {
            "help": "Subcommands for dealing with packages",
            "subc": {
                "list": {
                    "func": subc_packages_list,
                    "arg": "pathname",
                },
            },
        },
        "source": {
            "help": "Subcommands for dealing with source ids",
            "subc": {
                "list": {
                    "func": subc_source_list,
                    "arg": "pathname",
                },
            },
        },
    }

    argparser_subc(args, subc_list)

    r = args.parse_args()

    if "TERMUX_VERSION" in os.environ:
        # Termux is a very annoying environment
        r.relpath = False
    else:
        r.relpath = True

    return r


def main():
    args = argparser()

    if not args.command:
        raise NotImplementedError("No default subcommand")
        # TODO: default

    if not hasattr(args, "func"):
        raise ValueError("Can not run this subcommand")

    result = args.func(args)
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
