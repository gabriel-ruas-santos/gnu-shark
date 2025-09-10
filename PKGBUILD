# Maintainer: Gabriel Ruas Santos <gabrielruass@protonmail.com>
pkgname=gnushark
pkgver=1.0.0
pkgrel=1
pkgdesc="HUB de drivers, otimizações e utilitários para jogos no Linux (GTK)"
arch=('any')
url="https://github.com/gabriel-ruas-santos/gnu-shark"
license=('GPL3')
depends=(
  'python' 'gtk3' 'python-gobject'
  'polkit' 'flatpak'                # usados em tempo de execução
  'bash' 'coreutils' 'grep' 'sed'   # utilitários básicos
)
optdepends=(
  'expect: interação automática com prompts de pacman/pamac'
  'pamac-gtk: backend alternativo de instalação'
  'paru: helper AUR'
  'yay: helper AUR'
  'zenity: diálogos gráficos adicionais'
)
source=(
  "gnu-shark-${pkgver}.tar.gz::https://github.com/gabriel-ruas-santos/gnu-shark/archive/refs/tags/v${pkgver}.tar.gz"
  "org.gnushark.GNUShark.desktop"
  "org.gnushark.runroot.policy"
  "gnushark-runroot.sh"
)
sha256sums=('SKIP')

build() {
  cd "${srcdir}/${pkgname}-${pkgver}"
  # nada a compilar
}

package() {
# App icon in hicolor theme
install -Dm644 "icons/org.gnushark.GNUShark.svg" \
  "$pkgdir/usr/share/icons/hicolor/scalable/apps/org.gnushark.GNUShark.svg" || true
for s in 256x256 128x128 96x96 64x64 48x48 32x32 24x24 22x22 16x16; do
  if [[ -f "icons/$s/apps/org.gnushark.GNUShark.png" ]]; then
    install -Dm644 "icons/$s/apps/org.gnushark.GNUShark.png" \
      "$pkgdir/usr/share/icons/hicolor/$s/apps/org.gnushark.GNUShark.png"
  fi
done
  cd "${srcdir}/${pkgname}-${pkgver}"

  # binário principal (script python)
  install -Dm755 "gnushark.py" "${pkgdir}/usr/bin/gnushark"

  # ícones (se existir pasta icons/)
  if [ -d "icons" ]; then
    # ícone principal
    install -Dm644 "icons/org.gnushark.GNUShark.png" \
      "${pkgdir}/usr/share/icons/org.gnushark.GNUShark.png" || true
    # demais ícones custom do app (se houver)
    find icons -type f -name "*.png" -o -name "*.svg" | while read -r f; do
      base="$(basename "$f")"
      install -Dm644 "$f" "${pkgdir}/usr/share/gnushark/icons/48x48/apps/${base}"
    done
  fi

  # desktop + metainfo
  install -Dm644 "packaging/org.gnushark.GNUShark.desktop" \
    "${pkgdir}/usr/share/applications/org.gnushark.GNUShark.desktop"
  install -Dm644 "packaging/org.gnushark.GNUShark.metainfo.xml" \
    "${pkgdir}/usr/share/metainfo/org.gnushark.GNUShark.metainfo.xml"

  # polkit (action + wrapper)
  install -Dm644 "packaging/polkit/org.gnushark.runroot.policy" \
    "${pkgdir}/usr/share/polkit-1/actions/org.gnushark.runroot.policy"
  install -Dm755 "packaging/polkit/gnushark-runroot" \
    "${pkgdir}/usr/libexec/gnushark-runroot"

  # exemplo de licença (ajuste conforme o arquivo de LICENSE do repositório)
  install -Dm644 "LICENSE" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"

            # Install .desktop (generated here, avoids needing a separate file)
            install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/org.gnushark.GNUShark.desktop" << 'EOF'
[Desktop Entry]
Name=GNUShark
GenericName=System Tweaks for Gaming
Comment=GPU/driver helpers and gaming tweaks
Exec=env GNUSK_ICONS_DIR=/usr/share/gnushark/icons gnushark
TryExec=gnushark
Icon=org.gnushark.GNUShark
Terminal=false
Type=Application
Categories=System;Settings;Utility;
Keywords=GPU;Drivers;Gaming;Steam;Wine;Proton;
StartupNotify=true
EOF
}

