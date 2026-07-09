PYTHON      ?= python3
VENV        := .venv
VENV_PY     := $(VENV)/bin/python
VENV_PIP    := $(VENV)/bin/pip
VERSION     := $(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
ARCH        := $(shell dpkg --print-architecture 2>/dev/null || echo amd64)
DEB_FILE    := seilio-billing_$(VERSION)_$(ARCH).deb

.PHONY: help venv install icons test run clean-pyc clean-build clean distclean deb install-deb uninstall-deb reinstall

help:
	@echo "seilio-billing $(VERSION) — available targets:"
	@echo "  make venv          create .venv (--system-site-packages) with factur-x/reportlab"
	@echo "  make install       alias for venv"
	@echo "  make icons         regenerate resources/icons/*.png"
	@echo "  make test          run the pytest suite inside .venv"
	@echo "  make run           launch the app from source (offscreen-safe: QT_QPA_PLATFORM=offscreen make run)"
	@echo "  make deb           build $(DEB_FILE)"
	@echo "  make install-deb   sudo apt install the built .deb (builds it first if missing)"
	@echo "  make uninstall-deb sudo apt remove the installed package"
	@echo "  make reinstall     uninstall-deb + deb + install-deb"
	@echo "  make clean         remove build artifacts (.deb, packaging/build, __pycache__, .pytest_cache)"
	@echo "  make distclean     clean + remove .venv"

# --- Environment ---------------------------------------------------------

venv: $(VENV)/.stamp

$(VENV)/.stamp: pyproject.toml
	$(PYTHON) -m venv --system-site-packages $(VENV)
	$(VENV_PIP) install --upgrade pip -q
	$(VENV_PIP) install -q factur-x reportlab pytest
	touch $@

install: venv

# --- Assets ---------------------------------------------------------------

icons: venv
	$(VENV_PY) resources/gen_icons.py

# --- Dev loop ---------------------------------------------------------------

test: venv
	$(VENV_PY) -m pytest tests/ -q

run: venv
	$(VENV_PY) -m seilio_billing.main

# --- Debian packaging -------------------------------------------------------

deb: venv icons
	./build_deb.sh

$(DEB_FILE): deb

install-deb: $(DEB_FILE)
	sudo apt install ./$(DEB_FILE)

uninstall-deb:
	sudo apt remove -y seilio-billing

reinstall: uninstall-deb deb install-deb

# --- Cleanup ------------------------------------------------------------

clean-pyc:
	find . -name '__pycache__' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -not -path './.venv/*' -delete

clean-build:
	rm -rf packaging/build
	rm -f seilio-billing_*.deb
	rm -rf .pytest_cache

clean: clean-pyc clean-build

distclean: clean
	rm -rf $(VENV)
