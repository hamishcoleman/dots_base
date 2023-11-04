Tools for managing dots files and keeping them in repositories

# dotsctl

Registers source dotfile locations and installs them into the environment.

First, prep your dotfiles with some metadata.  eg:

```
#!/blah
#
# :dotsctl:
#   destdir: ~/bin/
# ...
```

The tool will look in the first page of code for the marker `:dotsctl:` and
use that to determine how many leading characters to remove.  All lines from
that point until the finishing `...` marker are then loaded as  YAML metadata.

possible keys include:

mkdir:
- a list of directories that this file needs
dest:
- the full path that this file should be installed to
destdir:
- the basename of this file will be appended to this dest dir to create the
  path that the file should be installed to
strip_extension:
- defaults to True, but can be set to False to disable stripping any extension
  when installing files

Usage:

`./dotsctl.py --help`
- Shows the subcommands available

`./dotsctl.py -v install .`
- Installs dotsctl itself

`dotsctl add .`
- Registers this subdir as a source for dotsctl files

`dotsctl install`
- Looks through all the registered sources and installs anything found
