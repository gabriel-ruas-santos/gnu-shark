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
	install -Dm644 packaging/org.gnushark.GNUShark.desktop "$(DESTDIR)/usr/share/applications/org.gnushark.GNUShark.desktop"
	install -Dm644 packaging/org.gnushark.GNUShark.metainfo.xml "$(DESTDIR)/usr/share/metainfo/org.gnushark.GNUShark.metainfo.xml"
	install -Dm644 packaging/polkit/org.gnushark.runroot.policy "$(DESTDIR)/usr/share/polkit-1/actions/org.gnushark.runroot.policy"
	install -Dm755 packaging/polkit/gnushark-runroot "$(DESTDIR)/usr/libexec/gnushark-runroot"
	@if [ -d icons ]; then \
	  install -Dm644 icons/org.gnushark.GNUShark.svg "$(DESTDIR)/usr/share/icons/hicolor/scalable/apps/org.gnushark.GNUShark.svg" || true; \
	  find icons -type f -name "*.png" -o -name "*.svg" | while read -r f; do \
	    base=$$(basename "$$f"); \
	    install -Dm644 "$$f" "$(DESTDIR)/usr/share/gnushark/icons/$$base"; \
	  done; \
	fi

uninstall:
	rm -f "$(DESTDIR)/usr/bin/gnushark"
	rm -f "$(DESTDIR)/usr/share/applications/org.gnushark.GNUShark.desktop"
	rm -f "$(DESTDIR)/usr/share/metainfo/org.gnushark.GNUShark.metainfo.xml"
	rm -f "$(DESTDIR)/usr/share/polkit-1/actions/org.gnushark.runroot.policy"
	rm -f "$(DESTDIR)/usr/libexec/gnushark-runroot"
	rm -rf "$(DESTDIR)/usr/share/gnushark"

lint:
	python -m pyflakes gnu-shark.py || true

run:
	python ./gnushark.py
