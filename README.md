Tools for managing dots files and keeping them in repositories

# dotsctl

Registers source dotfile locations and installs them into the environment.

The tool will look in the first 30 lines of each source file for a marker
string. (See the end of this file for an example)

This string is both used to define the beginning of a metadata block and to
determine how many leading characters to delete from each line in the metadata
block.  This is a way to support the comment characters used in multiple
different languages and config file formats without explicitly coding for it.

The end of the metadata block is a correctly indented `...`

Once the whole metadata block has been extracted and unindented, it is
interpreted as YAML.

possible keys include:

key     | Description
------- | -----------
mkdir:  | a string or a list of directories to make
symlink:| a dictionary of symlinks to create
dest:   | the full path that this file should be installed to
destdir:| the basename of the containing file will be appended to this dest dir to create the path that the file should be installed to
strip_extension: | defaults to True, but can be set to False to disable stripping any extension when installing files
dotsctl:| a dict of faked "filenames" and their dotsctl info to install
dpkg:   | A list of debian package names that this file needs

Usage:

`./dotsctl.py --help`
- Shows the subcommands available

`./dotsctl.py -v install .`
- Installs dotsctl itself

`dotsctl add .`
- Registers this subdir as a source for dotsctl files

`dotsctl install`
- Looks through all the registered sources and installs anything found

# Example metadata block

(Located at the end of the file to avoid this file being detected by the
dotsctl system)

```
#!/blah
#
# :dotsctl:
#   destdir: ~/bin/
# ...
```
