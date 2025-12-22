
PACKAGES+=flake8
PACKAGES+=python3-yaml

all:
	@echo Pure Python package - nothing to build

build-dep:
	sudo apt-get install $(PACKAGES)

lint:
	flake8
