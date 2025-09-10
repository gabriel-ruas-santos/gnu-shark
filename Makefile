.ONESHELL:
SHELL := /bin/sh
# --- injected variables for metainfo ---
METAINFO := $(SHARE)/metainfo
# --- injected variables for desktop/icons ---
PREFIX ?= /usr
DESTDIR ?=
APPID := org.gnushark.GNUShark
SHARE := $(DESTDIR)$(PREFIX)/share
HICOLOR := $(SHARE)/icons/hicolor
APPICONDIR := $(SHARE)/gnushark/icons
APP=gnushark
VERSION=1.0.0
TARBALL=$(APP)-$(VERSION).tar.gz

.PHONY: dist install uninstall lint run

dist:
	@git diff --quiet || (echo ">> Commit suas mudanças antes do dist"; exit 1)
	@git tag -l v$(VERSION) >/dev/null || echo ">> Dica: crie a tag v$(VERSION)"
	git archive --format=tar.gz --prefix=$(APP)-$(VERSION)/ -o $(TARBALL) HEAD
	@echo ">> gerado $(TARBALL)"

install:
	install -Dm755 gnushark.py "$(DESTDIR)/usr/bin/gnushark"
	
	# .desktop
	install -Dm644 /dev/stdin "$(DESTDIR)/usr/share/applications/$(APPID).desktop" <<- 'EOF'
	[Desktop Entry]
	Name=GNU/Shark
	GenericName=System Tweaks for Gaming
	Comment=Drivers, optimizations, and utilities hub for Linux games
	Exec=env GNUSK_ICONS_DIR=/usr/share/gnushark/icons gnushark
	TryExec=gnushark
	Icon=$(APPID)
	Terminal=false
	Type=Application
	Categories=System;Settings;Utility;
	Keywords=GPU;Drivers;Gaming;Steam;Wine;Proton;
	StartupNotify=true
	EOF
	
	# AppStream metainfo
	install -Dm644 /dev/stdin "$(METAINFO)/org.gnushark.GNUShark.metainfo.xml" <<- 'EOF'
	<?xml version="1.0" encoding="UTF-8"?>
	<component type="desktop-application">
	  <id>$(APPID)</id>
	  <name>GNUShark</name>
	  <summary>System tweaks for gaming (GPU/drivers)</summary>
	  <description>
	    <p>GNUShark provides handy tools to manage GPU/driver settings and gaming-oriented tweaks.</p>
	  </description>
	  <launchable type="desktop-id">$(APPID).desktop</launchable>
	  <metadata_license>CC0-1.0</metadata_license>
	  <developer_name>GNUShark Project</developer_name>
	</component>
	EOF
	
	install -Dm644 packaging/polkit/org.gnushark.runroot.policy "$(DESTDIR)/usr/share/polkit-1/actions/org.gnushark.runroot.policy"
	install -Dm755 packaging/polkit/gnushark-runroot "$(DESTDIR)/usr/libexec/gnushark-runroot"
	@if [ -d icons ]; then \
	  install -Dm644 icons/org.gnushark.GNUShark.png "$(DESTDIR)/usr/share/icons/org.gnushark.GNUShark.png" || true; \
	  find icons -type f -name "*.png" -o -name "*.svg" | while read -r f; do \
	    base=$$(basename "$$f"); \
	    install -Dm644 "$$f" "$(DESTDIR)/usr/share/gnushark/icons/48x48/apps/$$base"; \
	  done; \
	fi

uninstall:
	# Binário e .desktop
	rm -f "$(DESTDIR)/usr/bin/gnushark"
	rm -f "$(DESTDIR)/usr/share/applications/$(APPID).desktop"

	# Ícones do tema hicolor
	for s in scalable 256x256 128x128 96x96 64x64 48x48 32x32 24x24 22x22 16x16; do \
	  if [ "$$s" = "scalable" ]; then \
	    rm -f "$(HICOLOR)/$$s/apps/$(APPID).svg"; \
	  else \
	    rm -f "$(HICOLOR)/$$s/apps/$(APPID).png"; \
	  fi; \
	done

	# Pacote local de ícones
	rm -rf "$(APPICONDIR)"

	# Metainfo
	rm -f "$(METAINFO)/$(APPID).metainfo.xml"

	# Polkit
	rm -f "$(DESTDIR)/usr/share/polkit-1/actions/org.gnushark.runroot.policy"
	rm -f "$(LIBEXECDIR)/gnushark-runroot"

lint:
	python -m pyflakes gnu-shark.py || true

run:
	python ./gnushark.py
