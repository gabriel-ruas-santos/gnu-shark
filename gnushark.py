#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GNU/Shark — UI GTK simples para instalar drivers, otimizações e ferramentas de jogos.

Principais recursos
-------------------
- I18N (PT/EN) com fallback seguro e log de chaves ausentes
- Seleção automática da fonte de instalação: Repositório oficial > Flatpak > AUR
- Execução privilegiada via polkit (pkexec) ou sudo com PATH "safe"
- Automação robusta para pacman/pamac (auto-yes apenas onde apropriado)
- Detecção de hardware (CPU/GPU) e bloqueio de itens incompatíveis
- ZRAM com ajuste automático (tamanho, compressão, swappiness) e relatório
- Multilib: ativação assistida quando necessário
- UI com grid spacing unificado, títulos e subtítulos (subtítulo 12pt)
- Heurísticas de tamanho de janela com base na workarea
- Fluxo dedicado para Flathub (submenu Repositórios)

Compatibilidade
---------------
Projetado para Arch Linux e derivadas (Manjaro, CachyOS, etc.), usando pacman/paru/yay/pamac quando disponíveis.

Requisitos de runtime
---------------------
- Python 3.8+
- GTK 3 (PyGObject)
- Ferramentas de sistema padrão (pacman, flatpak, etc. conforme seu uso)
"""

from __future__ import annotations

import json
import locale
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOG = logging.getLogger("gnushark")

# =============================================================================
# GTK imports
# =============================================================================

import gi  # type: ignore
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # type: ignore

# X11 detection (opcional em tempo de execução)
try:
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11  # type: ignore
except Exception:
    GdkX11 = None  # type: ignore


def is_x11() -> bool:
    """Retorna True se a sessão atual for X11."""
    try:
        disp = Gdk.Display.get_default()
        return (GdkX11 is not None) and isinstance(disp, GdkX11.X11Display)
    except Exception:
        return False


# =============================================================================
# I18N
# =============================================================================

def _detect_ui_lang() -> str:
    """
    Retorna 'pt' ou 'en' com base no idioma do sistema.
    Ordem de checagem (primeira vitória):
      1) GLib.get_language_names() (respeita configuração do ambiente GTK)
      2) $LANGUAGE, $LC_ALL, $LC_MESSAGES, $LANG
      3) locale.getlocale(LC_MESSAGES) / locale.getlocale()
    Qualquer outro idioma => 'en' (fallback seguro).
    """
    def _norm(v: str) -> str:
        return v.split('.')[0].replace('_', '-').lower().strip() if v else ""

    # 1) Preferir GLib (respeita o ambiente do processo/desktop)
    try:
        langs = GLib.get_language_names() or []
        for cand in langs:
            c = _norm(cand)
            if c.startswith("pt"):
                return "pt"
            if c.startswith("en"):
                return "en"
    except Exception:
        pass

    # 2) Variáveis de ambiente comuns (inclui LANGUAGE)
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val:
            val = _norm(val)
            if val.startswith("pt"):
                return "pt"
            if val.startswith("en"):
                return "en"

    # 3) locale.getlocale
    loc = ""
    try:
        loc = (locale.getlocale(getattr(locale, "LC_MESSAGES", locale.LC_ALL))[0] or "")
    except Exception:
        pass
    if not loc:
        try:
            loc = (locale.getlocale()[0] or "")
        except Exception:
            loc = ""

    loc = _norm(loc)
    if loc.startswith("pt"):
        return "pt"
    if loc.startswith("en"):
        return "en"
    return "en"


UI_LANG = _detect_ui_lang()

# Traduções: a chave SEMPRE é o texto original em PT.
_TRANSL: Dict[str, Dict[str, str]] = {
    "en": {
        # Cabeçalho / geral
        "Um HUB de ferramentas e utilitários para jogos no Linux.": "A hub of tools and utilities for gaming on Linux.",
        "Wiki": "Wiki",
        "Reportar Bug": "Report a bug",
        "Sobre": "About",
        "Página do projeto": "Project page",
        # Polkit / permissões
        "Executar tarefas administrativas do GNU/Shark": "Run administrative tasks for GNU/Shark",
        "Permitir que o GNU Shark execute ações com privilégios administrativas?": "Allow GNU/Shark to perform administrative actions?",
        # About
        "Desenvolvido por Gabriel Ruas Santos": "Developed by Gabriel Ruas Santos",

        # Cards e descrições
        "Drivers": "Drivers",
        "Otimizações": "Optimizations",
        "Ferramentas": "Tools",
        "Extras": "Extras",
        "Repositórios": "Repositories",
        "Repositórios adicionais": "Additional repositories",
        "Drivers e runtimes necessários para sua GPU.": "Drivers and runtimes required for your GPU.",
        "Ajustes de desempenho para jogos.": "Performance tweaks for gaming.",
        "Gerenciadores de jogos e utilitários.": "Game launchers and utilities.",
        "Recursos adicionais e opcionais.": "Additional and optional resources.",
        "Ajustes de desempenho para melhorar a experiência em jogos.": "Performance tweaks to improve your gaming experience.",
        "Gerenciadores de jogos e utilitários complementares.": "Game managers and complementary utilities.",
        "Recursos adicionais e opcionais para usuários avançados.": "Additional and optional resources for advanced users.",

        # Itens e tooltips
        "Intel Mesa": "Intel Mesa",
        "NVIDIA Proprietário": "NVIDIA Proprietary",
        "AMD Mesa/RADV": "AMD Mesa/RADV",
        "Driver NVIDIA oficial + Vulkan (loader).": "Official NVIDIA driver + Vulkan (loader).",
        "Drivers Intel (Mesa) + Vulkan (loader e ICD).": "Intel drivers (Mesa) + Vulkan (loader and ICD).",
        "Drivers AMD (Mesa/RADV) + Vulkan (loader e ICD).": "AMD drivers (Mesa/RADV) + Vulkan (loader and ICD).",

        "GameMode": "GameMode",
        "Ativa otimizações de performance enquanto joga": "Enables performance optimizations while gaming",
        "Tuned": "Tuned",
        "Perfis automáticos de performance e economia de energia": "Automatic performance and power-saving profiles",
        "cpupower": "cpupower",
        "Ajusta frequência e modos de energia da CPU": "Adjust CPU frequency and power modes",
        "Zram": "Zram",
        "Configurar compressão de memória RAM para melhorar desempenho": "Configure compressed RAM (zram) to improve performance",
        "Preload": "Preload",
        "Daemon que pré-carrega apps para abrir mais rápido": "Daemon that preloads apps to open faster",

        "Steam": "Steam",
        "Cliente oficial de jogos": "Official game client",
        "Lutris": "Lutris",
        "Gerenciador de jogos para rodar títulos nativos, Wine e emuladores": "Game manager for native titles, Wine and emulators",
        "Heroic": "Heroic",
        "Cliente alternativo para Epic Games Store e GOG": "Alternative client for Epic Games Store and GOG",
        "ProtonPlus": "ProtonPlus",
        "Gerenciador de versões do ProtonGE para compatibilidade de jogos": "ProtonGE versions manager for game compatibility",
        "Wine": "Wine",
        "Camada de compatibilidade para rodar aplicativos do Windows": "Compatibility layer to run Windows applications",
        "Bottles": "Bottles",
        "Gerenciador de aplicações e jogos Windows em garrafas Wine isoladas": "Manager for Windows apps/games in isolated Wine bottles",
        "MangoHUD": "MangoHUD",
        "Exibe FPS e métricas de desempenho durante os jogos": "Display FPS and performance metrics in-game",
        "Steam Acolyte": "Steam Acolyte",
        "Ferramenta CLI para configurar multiplas contas Steam": "CLI tool to manage multiple Steam accounts",

        "Goverlay": "Goverlay",
        "Interface gráfica para MangoHUD e afins": "GUI for MangoHUD and related tools",
        "Python Steam": "Python Steam",
        "Biblioteca Python para API do Steam": "Python library for the Steam API",
        "CoreCtrl (AMD)": "CoreCtrl (AMD)",
        "Controle avançado de GPU/CPU AMD com perfis de energia": "Advanced AMD GPU/CPU control with power profiles",
        "GWE (NVIDIA)": "GWE (NVIDIA)",
        "GreenWithEnvy: Monitorar e controlar GPU NVIDIA (clocks, temperatura, ventoinha)": "GreenWithEnvy: Monitor and control NVIDIA GPU (clocks, temperature, fan)",
        "AdwSteamGtk": "AdwSteamGtk",
        "Deixa o Steam no visual GNOME/libadwaita": "Give Steam a GNOME/libadwaita look",

        # Diálogos / botões comuns
        "Instalação": "Installation",
        "Cancelar": "Cancel",
        "OK": "OK",
        "Abrir": "Open",
        "Abrir {label} agora?": "Open {label} now?",
        "Confirmar": "Confirm",
        "Instalar {label} via Flatpak?": "Install {label} via Flatpak?",
        "Nada a instalar": "Nothing to install",
        "Não há pacotes pendentes para {label}.": "There are no pending packages for {label}.",
        "Instalar {pkgs_str}?": "Install {pkgs_str}?",
        "Processo finalizado.": "Process finished.",
        # Multilib & AUR
        "Multilib": "Multilib",
        "Alguns pacotes 32-bit requerem o repositório [multilib].\n\nAtivar automaticamente e atualizar bancos de dados agora?": "Some 32-bit packages require the [multilib] repository.\n\nEnable it automatically and refresh databases now?",
        "Ative manualmente em /etc/pacman.conf e rode: sudo pacman -Syy": "Enable it manually in /etc/pacman.conf and run: sudo pacman -Syy",
        "AUR": "AUR",
        "Instalação abortada por falta de helper AUR.": "Installation aborted due to missing AUR helper.",
        "AUR helper ausente": "Missing AUR helper",
        # Execução/headless
        "Concluído (modo sem terminal)": "Completed (headless mode)",
        "Execução finalizada.\nLog salvo em: {log_path}\n\nVocê pode abrir o arquivo de log para detalhes.": "Execution finished.\nLog saved at: {log_path}\n\nYou can open the log file for details.",
        "Falha na execução": "Execution failure",
        "Falha ao abrir": "Failed to open",
        "Não foi possível iniciar '{exe}'.\n\n{e}": "Could not start '{exe}'.\n\n{e}",
        "Não foi possível construir o script de instalação (helper AUR ausente?).": "Couldn't build the installation script (missing AUR helper?).",
        # Hardware incompatível
        "Hardware incompatível": "Incompatible hardware",
        "Não detectei GPU NVIDIA neste sistema. Instalação do driver NVIDIA foi bloqueada.": "No NVIDIA GPU detected on this system. NVIDIA driver installation was blocked.",
        "Processador AMD detectado e nenhuma GPU Intel identificada. Instalação de drivers Intel foi bloqueada.": "AMD CPU detected and no Intel GPU identified. Intel driver installation was blocked.",
        "Não detectei GPU Intel neste sistema. Instalação de drivers Intel foi bloqueada.": "No Intel GPU detected on this system. Intel driver installation was blocked.",
        "Não detectei GPU AMD neste sistema. Instalação de drivers AMD foi bloqueada.": "No AMD GPU detected on this system. AMD driver installation was blocked.",
        # Kernel headers / NVIDIA flow
        "Atenção": "Attention",
        "Instale os headers do kernel e tente novamente para usar nvidia-dkms.": "Install kernel headers and try again to use nvidia-dkms.",
        "Headers do kernel": "Kernel headers",
        "Kernel atual: {ver}\nPara compilar módulos DKMS (ex.: nvidia-dkms) é recomendado instalar {cand}.\n\nInstalar agora?": "Current kernel: {ver}\nTo build DKMS modules (e.g., nvidia-dkms) it's recommended to install {cand}.\n\nInstall now?",
        "Instalação de {cand} iniciada. Assim que concluir, volte e tente novamente.": "Installation of {cand} started. Once finished, come back and try again.",
        "NVIDIA: regenerar initramfs": "NVIDIA: regenerate initramfs",
        "Detectei o driver NVIDIA carregado.\nRegenerar initramfs agora com {tool}?": "NVIDIA driver seems loaded.\nRegenerate initramfs now with {tool}?",
        "Reiniciar": "Reboot",
        "Reiniciar o sistema agora?": "Reboot the system now?",
        # Pós-instalação / info
        "Serviço ativado.\n\nResultado do teste:\n{out}": "Service enabled.\n\nTest result:\n{out}",
        "zram configurado": "zram configured",
        "ZRAM ajustado automaticamente:": "ZRAM automatically tuned:",
        "• Tamanho:": "• Size:",
        "• Compressão:": "• Compression:",
        "• vm.swappiness:": "• vm.swappiness:",
        "Estado atual (swapon --show):": "Current state (swapon --show):",
    }
}

# I18N extra (PT→EN) para fluxo Flatpak/Flathub e submenu Repositórios
_TRANSL["en"].update({
    "Flathub Ativo": "Flathub Active",
    "O suporte a flatpak já está habilitado em seu sistema.": "Flatpak support is already enabled on your system.",
    "Ativar o suporte a Flatpak e adicionar o repositório Flathub agora?": "Enable Flatpak support and add the Flathub repository now?",
    "Ativar o repositório Flathub agora?": "Enable the Flathub repository now?",
    "Configuração do Flatpak": "Flatpak setup",
    "Configuração do Flathub": "Flathub setup",

    "Repositórios": "Repositories",
    "Flathub": "Flathub",
    "Repositórios adicionais": "Additional repositories",
    "Uma seleção de repositórios adicionais.": "A selection of additional repositories.",
    "Repositório essencial para aplicativos flatpak": "Essential repository for Flatpak apps",

    "Fontes de software e repositórios.": "Software sources and repositories.",
    "Ativar/gerenciar o repositório Flathub": "Enable/manage the Flathub repository",
})

# Traduções faltantes adicionadas
_TRANSL["en"].update({
    "Instalar suporte multimídia (GStreamer) para o Wine?": "Install multimedia support (GStreamer) for Wine?",
})

def T(pt_text: str, **fmt) -> str:
    """
    Traduz PT→EN quando necessário. Placeholders via .format(**fmt).

    Observação:
    - Se a chave não existir no dicionário em EN, cai no texto PT e loga em DEBUG.
    - Se a função receber um texto já em EN (por chamadas encadeadas), ela o retorna como veio.
    """
    if UI_LANG == "pt":
        return pt_text.format(**fmt) if fmt else pt_text
    d = _TRANSL.get("en", {})
    txt = d.get(pt_text, pt_text)
    if txt == pt_text:  # loga chaves PT que não têm tradução
        LOG.debug("i18n: missing key for en: %r", pt_text)
    return txt.format(**fmt) if fmt else txt


# =============================================================================
# Constantes / Paths / Theme
# =============================================================================

APP_TITLE = "GNU/Shark"
APP_SUBTITLE = "Um HUB de ferramentas e utilitários para jogos no Linux."
APP_VERSION = "1.0.0"  # <<< NOVO: versão exibida no diálogo Sobre e usada no CLI --version

# App ID e nome do ícone (deve casar com o .desktop)
APP_ID = "org.gnushark.GNUShark"
APP_ICON_NAME = APP_ID

# Layout/cards
CARD_MIN_WIDTH = 440
CARD_MIN_HEIGHT = 88
CARD_ICON_PX = int(os.environ.get("GNUSK_CARD_ICON_PX", "40"))
HEADER_ICON_PX = int(os.environ.get("GNUSK_HEADER_ICON_PX", "48"))
MAIN_HEADER_ICON_PX = int(os.environ.get("GNUSK_MAIN_HEADER_ICON_PX", "72"))
TRANSITION_MS = int(os.environ.get("GNUSK_SWAP_MS", "420"))
GRID_SP = int(os.environ.get("GNUSK_GRID_SP", "28"))

# Config
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = XDG_CONFIG_HOME / "gnushark"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Icons
ICONS_DIR_NAME = "icons"
ICON_EXTS = (".svg", ".png", ".xpm")
ENABLE_ICON_RGLOB = os.environ.get("GNUSK_ICON_RGLOB", "0") == "1"

# Polkit
RUNROOT_POLICY_ID = "org.gnushark.runroot"
RUNROOT_WRAPPER_PATH = "/usr/libexec/gnushark-runroot"
RUNROOT_POLICY_PATH = f"/usr/share/polkit-1/actions/{RUNROOT_POLICY_ID}.policy"

# CSS (subtítulo 12pt)
CSS = """
window { background-color: #2b2a33; color: #e6e6e6; font-family: "Inter","Ubuntu","Cantarell",sans-serif; font-size: 11pt; }
.header { padding: 18px 18px 8px 18px; }
.header-title { font-weight: 700; font-size: 18pt; }
.header-subtitle { opacity: 0.85; font-size: 12pt; }
.card-btn { background-color:#3a3946; border-radius:18px; padding:14px; }
.card-btn:hover { background-color:#434255; } .card-btn:active{ background-color:#313041; }
.row { margin: 6px 0; }
.btn-label { font-weight: 700; font-size: 15pt; }
.footer { padding: 8px 14px 14px 14px; border-top-width: 1px; border-top-style: solid; border-top-color: rgba(255,255,255,0.08); }
.section { padding: 8px 14px 0 14px; opacity: 0.9; }
"""

# =============================================================================
# EXPECT + helpers shell
# =============================================================================
EXPECT_FUNC = r"""
expect_yes_pac() {
  set -o pipefail
  # $1 = comando a ser rodado (pode referenciar run_root/run_root_sh)
  if command -v expect >/dev/null 2>&1; then
    expect -c '
      set timeout -1
      set cmd [lindex $argv 0]
      # Força locale C para estabilizar prompts
      spawn env LC_ALL=C bash -lc "$cmd"
      puts ">>> running: $cmd"
      expect {
        # Confirmar apenas operações de instalação/continuidade/substituição
        -re {(?i)(::\s*)?(Proceed|Install|Continue|Replace)[^?\n]*\?} { send "y\r"; exp_continue }
        -re {(?i)(::\s*)?Import[^.\n]*PGP[^?\n]*\?} { send "y\r"; exp_continue }
        # Nunca confirmar remoções automaticamente
        -re {(?i)\b(Remove|Remover)\b[^?\n]*\?} { send "n\r"; exp_continue }
        # Prompts em PT (sim): Deseja/Continuar/Substituir/Conflit(o)
        -re {(?i)(Deseja|Continuar|Substituir|Conflit)[^?\n]*\?} { send "s\r"; exp_continue }
        -re {(?i)press[^\n]*enter[^\n]*continue} { send "\r"; exp_continue }
        eof
      }
    ' "$1"
  else
    _cmd="$1"
    _first="$(printf "%s" "$_cmd" | awk '{print $1}')"
    case "$_first" in
      pacman|pamac) yes | env LC_ALL=C bash -lc "$_cmd" ;;
      *)            eval "$_cmd" ;;
    esac
  fi
}
""".strip()


# =============================================================================
# Util: Diretórios, Tema e Ícones
# =============================================================================

def app_dir() -> Path:
    """Retorna o diretório da aplicação (compatível com PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


APP_DIR: Path = app_dir()
_ICONS_ENV = os.environ.get("GNUSK_ICONS_DIR")
ICONS_DIR: Path = Path(_ICONS_ENV) if _ICONS_ENV else (APP_DIR / ICONS_DIR_NAME)

def add_css() -> None:
    """Carrega o CSS custom do app."""
    prov = Gtk.CssProvider()
    prov.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )

def init_icon_theme() -> None:
    """Inclui o diretório de ícones custom no tema atual."""
    theme = Gtk.IconTheme.get_default()
    theme.append_search_path(str(ICONS_DIR))

class IconCategory(Enum):
    APPS = "apps"; DEVICES = "devices"; MIMETYPES = "mimetypes"; STATUS = "status"
    ACTIONS = "actions"; CATEGORIES = "categories"; PREFERENCES = "preferences"; PLACES = "places"

ICON_SIZES: Tuple[str, ...] = ("16x16","22x22","24x24","32x32","48x48","64x64","96x96","128x128","256x256","scalable")
ICON_CATEGORIES: Tuple[str, ...] = tuple(c.value for c in IconCategory)

ICON_ALIASES: Dict[str, str] = {
    "drivers": "drivers", "opt": "opt", "tools": "tools",
    "intel": "intel", "amd": "amd", "nvidia": "nvidia",
    "gamemode": "gamemode", "tuned": "tuned", "cpupower": "cpupower", "zram": "zram",
    "steam": "steam", "lutris": "lutris", "heroic": "heroic", "protonplus": "protonplus",
    "wine": "wine", "bottles": "bottles", "goverlay": "goverlay", "python-steam": "python-steam",
    "corectrl": "corectrl", "gwe": "gwe", "adwsteamgtk": "adwsteamgtk",
    # Novos aliases p/ ícones personalizados do submenu Repositórios
    "flathub": "flathub",
    "repository": "repository",
}

@lru_cache(maxsize=256)
def find_local_icon_file(name: str) -> Optional[Path]:
    """Procura um ícone local por nome/alias nas pastas do tema do app."""
    if not name:
        return None
    key = ICON_ALIASES.get(name, name)
    for ext in ICON_EXTS:
        direct = ICONS_DIR / f"{key}{ext}"
        if direct.exists():
            return direct
    for size in ICON_SIZES:
        for cat in ICON_CATEGORIES:
            for ext in ICON_EXTS:
                candidate = ICONS_DIR / size / cat / f"{key}{ext}"
                if candidate.exists():
                    return candidate
    if ENABLE_ICON_RGLOB and ICONS_DIR.exists():
        for path in ICONS_DIR.rglob(f"{key}*"):
            if path.suffix.lower() in ICON_EXTS and path.is_file():
                return path
    return None

def icon_name_or_fallback(name: str, fallback: str = "applications-system") -> str:
    """Resolve ícone local/tema; retorna fallback se não encontrado."""
    theme = Gtk.IconTheme.get_default()
    local = find_local_icon_file(name)
    if local:
        return str(local)
    if theme and theme.has_icon(name):
        return name
    alias = ICON_ALIASES.get(name)
    if alias and theme and theme.has_icon(alias):
        return alias
    return fallback

def build_icon(icon_ref: str, px: int) -> Gtk.Image:
    """Cria Gtk.Image a partir de arquivo local (escalado) ou nome de ícone do tema."""
    try:
        local: Optional[Path] = None
        if icon_ref:
            direct = Path(icon_ref)
            local = direct if direct.exists() else find_local_icon_file(icon_ref)
        if local:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(local), px, px, True)
                return Gtk.Image.new_from_pixbuf(pb)
            except Exception:
                return Gtk.Image.new_from_file(str(local))
        name = icon_name_or_fallback(icon_ref)
        img = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DIALOG)
        img.set_pixel_size(px)
        return img
    except Exception:
        fallback = Gtk.Image.new_from_icon_name("applications-system", Gtk.IconSize.DIALOG)
        fallback.set_pixel_size(px)
        return fallback

def card_icon(icon_ref: str) -> Gtk.Image:
    """Convenience para ícones de cards."""
    return build_icon(icon_ref, CARD_ICON_PX)

def _bootstrap_app_identity() -> None:
    """Define app-id, nome e ícone padrão (com fallback para arquivo local)."""
    try:
        GLib.set_prgname(APP_ID)              # Wayland: precisa casar com .desktop
        GLib.set_application_name(APP_TITLE)  # nome legível
    except Exception:
        pass

    # garantir diretório de ícones custom no tema
    init_icon_theme()

    # preferir arquivo local se existir
    local = find_local_icon_file(APP_ICON_NAME)
    if local:
        try:
            Gtk.Window.set_default_icon_from_file(str(local))
            return
        except Exception:
            pass
    Gtk.Window.set_default_icon_name(APP_ICON_NAME)


# =============================================================================
# Persistência
# =============================================================================

def load_state() -> Dict:
    """Carrega estado do app (JSON) se existir."""
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_state(data: Dict) -> None:
    """Salva estado do app (JSON)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def clean_legacy_state() -> None:
    """Remove chaves legadas do estado."""
    st = load_state(); changed = False
    for key in ("repos", "pick"):
        if key in st:
            st.pop(key, None); changed = True
    if changed:
        save_state(st)


# =============================================================================
# Distro / PKG manager
# =============================================================================

def detect_distro() -> Tuple[str, str]:
    """Retorna (id, nome legível) da distro."""
    distro_id = ""; id_like = ""; pretty = ""
    try:
        kv = dict(
            (k.strip(), v.strip().strip('"'))
            for k, v in (
                line.split("=", 1)
                for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
        )
        distro_id = kv.get("ID", "").lower()
        id_like = kv.get("ID_LIKE", "").lower()
        pretty = kv.get("PRETTY_NAME", kv.get("NAME", ""))
    except Exception:
        pass

    def has(tok: str) -> bool:
        return tok in distro_id or tok in id_like

    if has("cachyos"):
        return "cachyos", pretty or "CachyOS"
    if has("biglinux"):
        return "biglinux", pretty or "BigLinux"
    if has("manjaro"):
        return "manjaro", pretty or "Manjaro"
    if distro_id == "arch" or "arch" in id_like:
        return "arch", pretty or "Arch Linux"
    return "unknown", pretty or "Linux"


def pick_pkg_manager() -> Optional[str]:
    """Retorna primeiro gerenciador encontrado dentre pamac/pacman/paru/yay."""
    for cand in ("pamac", "pacman", "paru", "yay"):
        if shutil.which(cand):
            return cand
    return None


# =============================================================================
# Detecção de hardware
# =============================================================================

def _run_cmd_get_output(cmd: str) -> str:
    """Executa comando em shell bash -lc e retorna saída (ou string vazia em erro)."""
    try:
        return subprocess.check_output(["bash", "-lc", cmd], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""

def detect_cpu_vendor() -> str:
    """Retorna fornecedor de CPU ('intel', 'amd' ou '')."""
    txt = ""
    try:
        if Path("/proc/cpuinfo").exists():
            txt = Path("/proc/cpuinfo").read_text(errors="ignore")
    except Exception:
        pass
    if not txt:
        txt = _run_cmd_get_output("lscpu || true")
    low = txt.lower()
    if "genuineintel" in low or "intel" in low:
        return "intel"
    if "authenticamd" in low or "amd" in low:
        return "amd"
    return ""

def _gpu_vendors_from_lspci() -> List[str]:
    out = _run_cmd_get_output("lspci -nnk | grep -iE 'vga|3d|display' -A2 || true").lower()
    found: List[str] = []
    if "nvidia" in out:
        found.append("nvidia")
    if "amd" in out or "ati" in out:
        found.append("amd")
    if "intel" in out:
        found.append("intel")
    return list(dict.fromkeys(found))

def _gpu_vendors_from_sysfs() -> List[str]:
    vendors: List[str] = []
    try:
        drm = Path("/sys/class/drm")
        if drm.exists():
            for dev in drm.glob("card*/device/vendor"):
                try:
                    vid = dev.read_text().strip().lower()
                    if vid.startswith("0x"):
                        vid = vid[2:]
                    if vid == "10de":
                        vendors.append("nvidia")
                    elif vid in ("1002",):
                        vendors.append("amd")
                    elif vid == "8086":
                        vendors.append("intel")
                except Exception:
                    pass
    except Exception:
        pass
    return list(dict.fromkeys(vendors))

def _gpu_modules_present() -> List[str]:
    out = _run_cmd_get_output("lsmod | awk '{print $1}' | tr '[:upper:]' '[:lower:]'")
    vendors: List[str] = []
    if "nvidia" in out:
        vendors.append("nvidia")
    if "amdgpu" in out or "radeon" in out:
        vendors.append("amd")
    if "i915" in out:
        vendors.append("intel")
    return list(dict.fromkeys(vendors))

def detect_gpu_vendors() -> List[str]:
    """Tenta detectar vendors pela ordem: lspci -> sysfs."""
    vendors = _gpu_vendors_from_lspci()
    if not vendors:
        vendors = _gpu_vendors_from_sysfs()
    return vendors


# =============================================================================
# UI helpers
# =============================================================================

def _primary_monitor_metrics() -> Tuple[int, int, int, int, int]:
    """Retorna (screen_w, screen_h, work_w, work_h, scale_factor)."""
    screen_w = screen_h = work_w = work_h = 0
    scale = 1
    try:
        disp = Gdk.Display.get_default()
        if disp:
            mon = None
            try:
                mon = disp.get_primary_monitor()
            except Exception:
                pass
            if mon is None:
                try:
                    mon = disp.get_monitor(0)
                except Exception:
                    mon = None
            if mon:
                geo = mon.get_geometry()
                screen_w, screen_h = int(geo.width), int(geo.height)
                try:
                    wa = mon.get_workarea()
                    work_w, work_h = int(wa.width), int(wa.height)
                except Exception:
                    work_w, work_h = screen_w, screen_h
                try:
                    scale = int(mon.get_scale_factor())
                except Exception:
                    scale = 1
    except Exception:
        pass

    if not screen_w or not screen_h:
        try:
            scr = Gdk.Screen.get_default()
            if scr:
                screen_w, screen_h = scr.get_width(), scr.get_height()
                work_w, work_h = screen_w, screen_h
        except Exception:
            pass

    if not work_w or not work_h:
        work_w, work_h = (screen_w or 1024), (screen_h or 768)
    return screen_w, screen_h, work_w, work_h, (scale or 1)

def _suggested_window_size(base_w: int = 980, base_h: int = 640) -> Tuple[int, int, int]:
    """Calcula tamanho proporcional que caiba na workarea."""
    _, _, work_w, work_h, _ = _primary_monitor_metrics()
    frac = float(os.environ.get("GNUSK_WIN_FRACTION", "0.92"))
    max_w = int(work_w * frac)
    max_h = int(work_h * frac)

    s = min(max_w / float(base_w), max_h / float(base_h), 1.0)
    s = max(s, 0.65)
    win_w = min(int(base_w * s), max_w)
    win_h = min(int(base_h * s), max_h)
    return win_w, win_h, work_h

def adjust_card_sizes_for_screen(screen_height: Optional[int] = None) -> None:
    """Ajusta mínimos dos cards usando a altura real (workarea)."""
    global CARD_MIN_WIDTH, CARD_MIN_HEIGHT
    try:
        h = int(screen_height) if screen_height else Gdk.Screen.get_default().get_height()  # type: ignore[union-attr]
    except Exception:
        h = 900

    if h < 720:
        CARD_MIN_WIDTH = 360; CARD_MIN_HEIGHT = 80
    elif h < 900:
        CARD_MIN_WIDTH = 420; CARD_MIN_HEIGHT = 86
    else:
        CARD_MIN_WIDTH = 440; CARD_MIN_HEIGHT = 88

def make_card_button(child_builder: Callable[[], Gtk.Widget], tooltip: Optional[str] = None) -> Gtk.Button:
    """Cria um botão “card” com estilo padrão."""
    btn = Gtk.Button()
    btn.get_style_context().add_class("card-btn")
    btn.set_halign(Gtk.Align.FILL); btn.set_valign(Gtk.Align.CENTER)
    btn.set_size_request(CARD_MIN_WIDTH, CARD_MIN_HEIGHT)
    if tooltip: btn.set_tooltip_text(tooltip)
    btn.add(child_builder()); return btn

def action_card(label: str, icon: str, on_click: Callable, tooltip: Optional[str] = None) -> Gtk.Button:
    """Card com ícone + rótulo centralizado."""
    def build() -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.get_style_context().add_class("row")
        row.pack_start(card_icon(icon), False, False, 0)
        lbl = Gtk.Label(label=label); lbl.set_xalign(0.5); lbl.set_yalign(0.5); lbl.set_hexpand(True)
        lbl.get_style_context().add_class("btn-label")
        row.pack_start(lbl, True, True, 0); return row
    btn = make_card_button(build, tooltip); btn.connect("clicked", on_click); return btn

def attach_in_two_columns(grid: Gtk.Grid, widgets: Sequence[Gtk.Widget]) -> None:
    """Anexa cards em grid 2 colunas com SizeGroup para alinhamento."""
    sg_w = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
    sg_h = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
    cols = 2; r = c = 0
    for w in widgets:
        sg_w.add_widget(w); sg_h.add_widget(w)
        grid.attach(w, c, r, 1, 1); c += 1
        if c >= cols: c = 0; r += 1

def _clear_container(box: Gtk.Container) -> None:
    """Remove todos os filhos de um container GTK."""
    for ch in list(box.get_children()):
        box.remove(ch)

def new_cards_grid() -> Gtk.Grid:
    """Grid padronizado (mesmo spacing V/H)."""
    g = Gtk.Grid()
    g.set_row_spacing(GRID_SP)
    g.set_column_spacing(GRID_SP)
    g.set_halign(Gtk.Align.CENTER)
    g.set_valign(Gtk.Align.CENTER)
    return g


# =============================================================================
# Submenu
# =============================================================================

class Submenu(Gtk.Box):
    """
    Container reutilizável para páginas de itens (Drivers/Otimizações/etc.).

    Parâmetros:
      - app_window: janela principal (para callbacks)
      - title: título da seção
      - menu_icon: ícone do cabeçalho
      - items: lista de itens com chaves {label,id,icon,tooltip}
      - section_key: chave lógica da seção
      - on_back: callback para voltar à tela principal
      - desc: descrição complementar (opcional)
    """
    def __init__(
        self,
        app_window: Gtk.Window,
        title: str,
        menu_icon: str,
        items: Sequence[Dict[str, str]],
        section_key: str,
        on_back: Callable[[], None],
        desc: str = ""
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.section_key = section_key; self.on_back = on_back; self.app_window = app_window
        self.set_border_width(10)

        if hasattr(self.app_window, "set_sub_header"):
            self.app_window.set_sub_header(title, self._back_clicked)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.get_style_context().add_class("header")
        header.pack_start(build_icon(menu_icon, HEADER_ICON_PX), False, False, 0)

        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t = Gtk.Label.new(title); t.set_xalign(0.0); t.get_style_context().add_class("header-title")
        s = Gtk.Label.new(desc); s.set_xalign(0.0); s.get_style_context().add_class("header-subtitle")
        v.pack_start(t, False, False, 0); v.pack_start(s, False, False, 0)
        header.pack_start(v, True, True, 0); self.pack_start(header, False, False, 0)

        sc = Gtk.ScrolledWindow(); sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); sc.set_vexpand(True)
        self.pack_start(sc, True, True, 0)

        grid_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        grid_wrap.set_halign(Gtk.Align.CENTER); grid_wrap.set_valign(Gtk.Align.CENTER); sc.add(grid_wrap)

        grid = new_cards_grid()
        grid_wrap.pack_start(grid, True, True, 0)

        cards: List[Gtk.Button] = []
        for it in items:
            btn = action_card(
                it["label"], it.get("icon","applications-system"),
                on_click=lambda _w, _it=it: self.app_window.handle_action(self.section_key, _it),
                tooltip=it.get("tooltip"),
            )
            cards.append(btn)
        attach_in_two_columns(grid, cards)

    def _back_clicked(self, *_args: object) -> None:
        """Callback do botão 'voltar' no HeaderBar."""
        if hasattr(self.app_window, "set_main_header"):
            self.app_window.set_main_header()
        self.on_back()


# =============================================================================
# Ações / Terminais
# =============================================================================

@dataclass(frozen=True)
class TerminalSpec:
    name: str
    args: List[str]
    needs_string: bool
    wayland_pref: bool

# Mapa de itens (pacotes, exec, flatpak, alternativas)
ACTION_MAP: Dict[str, Dict[str, object]] = {
    "intel-mesa": {"packages": ["mesa", "vulkan-intel", "lib32-vulkan-intel", "vulkan-icd-loader", "lib32-vulkan-icd-loader"]},
    "amd-mesa":   {"packages": ["mesa", "vulkan-radeon", "lib32-vulkan-radeon", "vulkan-icd-loader", "lib32-vulkan-icd-loader"]},
    "gamemode":   {"packages": ["gamemode", "lib32-gamemode"]},
    "tuned-performance": {"packages": ["tuned"]},
    "cpupower-performance": {"packages": ["cpupower"]},
    "zram":       {"packages": ["zram-generator"]},
    "preload":    {"packages": ["preload"]},

    "steam":   {"packages": ["steam"], "exec": "steam", "flatpak": "com.valvesoftware.Steam"},
    "lutris":  {"packages": ["lutris"], "exec": "lutris", "flatpak": "net.lutris.Lutris"},
    "heroic":  {"packages": ["heroic-games-launcher"], "exec": "heroic", "flatpak": "com.heroicgameslauncher.hgl"},

    "protonplus": {"packages": ["protonplus"], "exec": "protonplus", "flatpak": "com.vysp3r.ProtonPlus"},

    # Wine completo + winecfg como exec para abrir caso tudo já esteja presente
    "wine": {
        "packages": [
            "wine","winetricks","dxvk-bin","vkd3d","vkd3d-proton",
            "samba"
        ],
        "exec": "winecfg"
    },

    "bottles": {"packages": ["bottles"], "exec": "bottles", "flatpak": "com.usebottles.bottles"},
    "mangohud": {"packages": ["mangohud", "lib32-mangohud"]},
    "steam-acolyte": {"packages": ["steam-acolyte"], "exec": "steam-acolyte"},
    "goverlay": {"packages": ["goverlay"], "exec": "goverlay"},
    "python-steam": {"packages": ["python-steam"]},
    "corectrl": {"packages": ["corectrl"], "exec": "corectrl"},
    "gwe": {"packages": ["gwe", "greenwithenvy"], "exec": "gwe", "flatpak": "com.leinardi.gwe"},
    "adwsteamgtk": {"packages": ["adwsteamgtk"], "exec": "adwsteamgtk", "flatpak": "io.github.Foldex.AdwSteamGtk"},
}

# Pacotes opcionais de multimídia para Wine (pergunta no fim da instalação)
GSTREAMER_WINE_PKGS: List[str] = [
    "gst-plugins-base","gst-plugins-good","gst-plugins-bad",
    "lib32-gst-plugins-base","lib32-gst-plugins-good","lib32-gst-plugins-bad",
]

TERMINALS: List[TerminalSpec] = [
    TerminalSpec("kgx", ["kgx","--","bash","-lc"], False, True),
    TerminalSpec("ghostty", ["ghostty","--","bash","-lc"], False, True),
    TerminalSpec("foot", ["foot","-e","bash","-lc"], False, True),
    TerminalSpec("footclient", ["footclient","-e","bash","-lc"], False, True),
    TerminalSpec("rio", ["rio","-e","bash","-lc"], False, True),
    TerminalSpec("wezterm", ["wezterm","start","bash","-lc"], False, True),
    TerminalSpec("gnome-terminal", ["gnome-terminal","--wait","--","bash","-lc"], False, False),
    TerminalSpec("konsole", ["konsole","-e","bash","-lc"], False, False),
    TerminalSpec("xterm", ["xterm","-e","bash","-lc"], False, False),
    TerminalSpec("terminator", ["terminator","-x","bash","-lc"], False, False),
    TerminalSpec("urxvt", ["urxvt","-e","bash","-lc"], False, False),
    TerminalSpec("rxvt", ["rxvt","-e","bash","-lc"], False, False),
    TerminalSpec("st", ["st","-e","bash","-lc"], False, False),
    TerminalSpec("eterm", ["eterm","-e","bash","-lc"], False, False),
    TerminalSpec("terminology", ["terminology","-e","bash","-lc"], False, False),
    TerminalSpec("alacritty", ["alacritty","-e","bash","-lc"], False, False),
    TerminalSpec("kitty", ["kitty","-e","bash","-lc"], False, False),
    TerminalSpec("tilix", ["tilix","--","bash","-lc"], False, False),
    TerminalSpec("xfce4-terminal", ["xfce4-terminal","--command"], True, False),
    TerminalSpec("mate-terminal", ["mate-terminal","--","bash","-lc"], False, False),
    TerminalSpec("qterminal", ["qterminal","-e","bash","-lc"], False, False),
    TerminalSpec("lxterminal", ["lxterminal","-e","bash","-lc"], False, False),
]


# =============================================================================
# App
# =============================================================================

@lru_cache(maxsize=1024)
def _pkg_in_official_repos_cached(pkg: str) -> bool:
    """Cache de checagem 'pacman -Si' para um pacote no repo oficial."""
    return subprocess.run(["bash","-lc",f"pacman -Si {shlex.quote(pkg)} >/dev/null 2>&1"]).returncode == 0

def _which_in_official_repos(pkgs: Iterable[str]) -> set:
    """Retorna subconjunto de pkgs que existem nos repositórios oficiais."""
    plist = [shlex.quote(p) for p in pkgs if p]
    if not plist:
        return set()
    cmd = "pacman -Si " + " ".join(plist) + " 2>/dev/null | awk -F': *' '/^Name/{print $2}'"
    try:
        out = subprocess.check_output(["bash","-lc",cmd], text=True)
        names = {line.strip() for line in out.splitlines() if line.strip()}
        return names
    except Exception:
        return {p for p in pkgs if _pkg_in_official_repos_cached(p)}

class App(Gtk.Window):
    """Janela principal do GNU/Shark."""

    def __init__(self) -> None:
        super().__init__(title=APP_TITLE)

        # Tamanho inicial inteligente
        win_w, win_h, work_h = _suggested_window_size(base_w=980, base_h=640)
        adjust_card_sizes_for_screen(work_h)
        self.set_default_size(win_w, win_h)
        self.set_border_width(14)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)

        # Integração X11
        if is_x11():
            try:
                self.set_wmclass("gnushark", "GNU Shark")
                self.set_role("gnushark")
                Gtk.Window.set_default_icon_name(APP_ICON_NAME)  # usa ícone do app
            except Exception:
                pass

        clean_legacy_state()
        self.distro_id, self.distro_pretty = detect_distro()
        self.pkg_manager = pick_pkg_manager()

        self.cpu_vendor = detect_cpu_vendor()
        self.gpu_vendors = detect_gpu_vendors()

        self._policy_lock = threading.Lock()
        self._policy_installing = False

        add_css()
        init_icon_theme()

        # Header
        self.hb = Gtk.HeaderBar(); self.hb.set_show_close_button(True); self.set_titlebar(self.hb)
        self.set_main_header()

        # Atalhos
        self.accel_group = Gtk.AccelGroup(); self.add_accel_group(self.accel_group)
        self._install_accel("<Control>q", self.on_quit); self._install_accel("F1", self.on_about)

        # Root
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.root)

        # Stack: main/sub
        self.stack = Gtk.Stack()
        self.stack.set_transition_duration(TRANSITION_MS)
        self.root.pack_start(self.stack, True, True, 0)

        self.page_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.page_sub  = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_named(self.page_main, "main")
        self.stack.add_named(self.page_sub,  "sub")
        self.stack.set_visible_child_name("main")

        self._build_main()
        self.show_all()
        self._init_post_steps()

    # ----- Header API -----

    def set_main_header(self) -> None:
        """Define o HeaderBar padrão (título + sem subtítulo)."""
        for child in list(self.hb.get_children()):
            self.hb.remove(child)
        self.hb.set_title(APP_TITLE); self.hb.set_subtitle(None)

    def set_sub_header(self, section_title: str, back_cb: Callable[..., None]) -> None:
        """Define HeaderBar para subpáginas com botão Voltar."""
        for child in list(self.hb.get_children()):
            self.hb.remove(child)
        self.hb.set_title(f"{APP_TITLE}: {section_title}")
        self.hb.set_subtitle(None)
        back_btn = Gtk.Button()
        back_btn.add(build_icon("go-previous-symbolic", 16))
        back_btn.connect("clicked", back_cb)
        self.hb.pack_start(back_btn)
        self.hb.show_all()

    # ----- Main UI -----

    def _build_main(self) -> None:
        """Constroi a página principal com cards de seções."""
        _clear_container(self.page_main)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.get_style_context().add_class("header")
        header.pack_start(build_icon(APP_ICON_NAME, MAIN_HEADER_ICON_PX), False, False, 0)  # ícone do app aqui

        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label.new(APP_TITLE); title.set_xalign(0.0); title.get_style_context().add_class("header-title")
        subtitle = Gtk.Label.new(T(APP_SUBTITLE)); subtitle.set_xalign(0.0); subtitle.get_style_context().add_class("header-subtitle")
        v.pack_start(title, False, False, 0); v.pack_start(subtitle, False, False, 0)
        header.pack_start(v, True, True, 0); main_box.pack_start(header, False, False, 0)

        grid = new_cards_grid()
        main_box.pack_start(grid, True, True, 0)

        cards = [
            action_card(T("Drivers"), "drivers", self.open_drivers, T("Drivers e runtimes necessários para sua GPU.")),
            action_card(T("Otimizações"), "opt", self.open_opt, T("Ajustes de desempenho para jogos.")),
            action_card(T("Ferramentas"), "tools", self.open_tools, T("Gerenciadores de jogos e utilitários.")),
            action_card(T("Repositórios"), "repository", self.open_repos, T("Repositórios adicionais")),
            action_card(T("Extras"), "applications-utilities", self.open_extras, T("Recursos adicionais e opcionais.")),
        ]
        attach_in_two_columns(grid, cards)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        footer.set_halign(Gtk.Align.CENTER); footer.get_style_context().add_class("footer")
        footer.pack_start(Gtk.LinkButton(uri="https://github.com/gabriel-ruas-santos/gnu-shark/wiki", label=T("Wiki")), False, False, 0)
        footer.pack_start(Gtk.LinkButton(uri="https://github.com/gabriel-ruas-santos/gnu-shark/issues", label=T("Reportar Bug")), False, False, 0)
        about_btn = Gtk.Button(label=T("Sobre")); about_btn.connect("clicked", self.on_about)
        footer.pack_start(about_btn, False, False, 0); main_box.pack_end(footer, False, False, 0)

        self.page_main.pack_start(main_box, True, True, 0)
        self.page_main.show_all()
        self.stack.set_visible_child_name("main")
        self.set_main_header()

    def _show_submenu(self, widget: Gtk.Widget) -> None:
        """Mostra uma subpágina com animação."""
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        _clear_container(self.page_sub)
        self.page_sub.pack_start(widget, True, True, 0)
        self.page_sub.show_all()
        self.stack.set_visible_child_name("sub")

    def back_to_main(self) -> None:
        """Volta para a página principal com animação."""
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
        self.stack.set_visible_child_name("main")
        self.set_main_header()

    # ----- Submenus -----

    def open_drivers(self, _btn: Gtk.Button) -> None:
        items = [
            {"label": T("Intel Mesa"), "id": "intel-mesa", "icon": "intel",
             "tooltip": T("Drivers Intel (Mesa) + Vulkan (loader e ICD).")},
            {"label": T("NVIDIA Proprietário"), "id": "nvidia-driver", "icon": "nvidia",
             "tooltip": T("Driver NVIDIA oficial + Vulkan (loader).")},
            {"label": T("AMD Mesa/RADV"), "id": "amd-mesa", "icon": "amd",
             "tooltip": T("Drivers AMD (Mesa/RADV) + Vulkan (loader e ICD).")},
        ]
        view = Submenu(self, T("Drivers"), "drivers", items, "drivers", self.back_to_main,
                       desc=T("Drivers e runtimes necessários para sua GPU."))
        self._show_submenu(view)

    def open_opt(self, _btn: Gtk.Button) -> None:
        items = [
            {"label": T("GameMode"), "id": "gamemode", "icon": "gamemode",
             "tooltip": T("Ativa otimizações de performance enquanto joga")},
            {"label": T("Tuned"), "id": "tuned-performance", "icon": "tuned",
             "tooltip": T("Perfis automáticos de performance e economia de energia")},
            {"label": T("cpupower"), "id": "cpupower-performance", "icon": "cpupower",
             "tooltip": T("Ajusta frequência e modos de energia da CPU")},
            {"label": T("Zram"), "id": "zram", "icon": "zram",
             "tooltip": T("Configurar compressão de memória RAM para melhorar desempenho")},
            {"label": T("Preload"), "id": "preload", "icon": "system-run",
             "tooltip": T("Daemon que pré-carrega apps para abrir mais rápido")},
        ]
        view = Submenu(self, T("Otimizações"), "opt", items, "opt", self.back_to_main,
                       desc=T("Ajustes de desempenho para melhorar a experiência em jogos."))
        self._show_submenu(view)

    def open_tools(self, _btn: Gtk.Button) -> None:
        items = [
            {"label": T("Steam"), "id": "steam", "icon": "steam", "tooltip": T("Cliente oficial de jogos")},
            {"label": T("Lutris"), "id": "lutris", "icon": "lutris", "tooltip": T("Gerenciador de jogos para rodar títulos nativos, Wine e emuladores")},
            {"label": T("Heroic"), "id": "heroic", "icon": "heroic", "tooltip": T("Cliente alternativo para Epic Games Store e GOG")},
            {"label": T("ProtonPlus"), "id": "protonplus", "icon": "protonplus", "tooltip": T("Gerenciador de versões do ProtonGE para compatibilidade de jogos")},
            {"label": T("Wine"), "id": "wine", "icon": "wine", "tooltip": T("Camada de compatibilidade para rodar aplicativos do Windows")},
            {"label": T("Bottles"), "id": "bottles", "icon": "bottles", "tooltip": T("Gerenciador de aplicações e jogos Windows em garrafas Wine isoladas")},
            {"label": T("MangoHUD"), "id": "mangohud", "icon": "utilities-system-monitor", "tooltip": T("Exibe FPS e métricas de desempenho durante os jogos")},
            {"label": T("Steam Acolyte"), "id": "steam-acolyte", "icon": "applications-system",
             "tooltip": T("Ferramenta CLI para configurar multiplas contas Steam")},
        ]
        view = Submenu(self, T("Ferramentas"), "tools", items, "tools", self.back_to_main,
                       desc=T("Gerenciadores de jogos e utilitários complementares."))
        self._show_submenu(view)

    def open_repos(self, _btn: Gtk.Button) -> None:
        """Submenu Repositórios (inclui card Flathub)."""
        items = [
            {
                "label": T("Flathub"),
                "id": "flathub",
                "icon": "flathub",  # ícone personalizado
                "tooltip": T("Repositório essencial para aplicativos flatpak"),
            },
        ]
        view = Submenu(
            self,
            T("Repositórios"),
            "repository",  # ícone personalizado
            items,
            "repos",
            self.back_to_main,
            desc=T("Uma seleção de repositórios adicionais.")
        )
        self._show_submenu(view)

    def open_extras(self, _btn: Gtk.Button) -> None:
        items = [
            {"label": T("Goverlay"), "id": "goverlay", "icon": "goverlay",
             "tooltip": T("Interface gráfica para MangoHUD e afins")},
            {"label": T("Python Steam"), "id": "python-steam", "icon": "python-steam",
             "tooltip": T("Biblioteca Python para API do Steam")},
            {"label": T("CoreCtrl (AMD)"), "id": "corectrl", "icon": "corectrl",
             "tooltip": T("Controle avançado de GPU/CPU AMD com perfis de energia")},
            {"label": T("GWE (NVIDIA)"), "id": "gwe", "icon": "gwe",
             "tooltip": T("GreenWithEnvy: Monitorar e controlar GPU NVIDIA (clocks, temperatura, ventoinha)")},
            {"label": T("AdwSteamGtk"), "id": "adwsteamgtk", "icon": "adwsteamgtk",
             "tooltip": T("Deixa o Steam no visual GNOME/libadwaita")},
        ]
        view = Submenu(self, T("Extras"), "applications-utilities", items, "extras", self.back_to_main,
                       desc=T("Recursos adicionais e opcionais para usuários avançados."))
        self._show_submenu(view)

    # ----- Atalhos -----

    def _install_accel(self, accel: str, callback: Callable[[Optional[Gtk.Widget]], None]) -> None:
        """Registra um atalho de teclado para a janela."""
        keyval, mod = Gtk.accelerator_parse(accel)
        def on_accel(*_args: object) -> bool:
            callback(None); return True
        self.accel_group.connect(keyval, mod, Gtk.AccelFlags.VISIBLE, on_accel)

    def on_quit(self, _btn: Optional[Gtk.Button]) -> None:
        """Fecha a aplicação."""
        Gtk.main_quit()

    # =============================================================================
    # Execução / instalação
    # =============================================================================

    def _wait_sentinel_then_notify(self, sentinel_path: str, restore_window: bool) -> None:
        """Espera a criação do arquivo-sentinela e só então mostra o 'Processo finalizado'."""
        deadline = time.monotonic() + 4 * 60 * 60  # 4h
        try:
            while time.monotonic() < deadline:
                if os.path.exists(sentinel_path):
                    try:
                        os.remove(sentinel_path)
                    except Exception:
                        pass
                    break
                time.sleep(1.0)
        finally:
            if restore_window:
                try:
                    GLib.idle_add(self.deiconify)
                    GLib.idle_add(self.present)
                except Exception:
                    pass
            GLib.idle_add(self._info, T("Instalação"), T("Processo finalizado."))

    # ---------- Resolver provedores virtuais ----------
    def _resolve_virtual_pkgs(self, pkgs: Sequence[str]) -> List[str]:
        """Troca nomes virtuais por provedores concretos para evitar prompts."""
        resolved: List[str] = []
        for p in pkgs:
            if p == "vkd3d-proton":
                if _pkg_in_official_repos_cached("vkd3d-proton"):
                    resolved.append("vkd3d-proton")
                elif _pkg_in_official_repos_cached("vkd3d-proton-bin"):
                    resolved.append("vkd3d-proton-bin")
                else:
                    resolved.append("vkd3d-proton-bin")
            else:
                resolved.append(p)
        return resolved

    # ---------- Checagens ----------
    def _missing_packages(self, pkgs: Sequence[str]) -> List[str]:
        """Retorna lista de pacotes ausentes (não instalados)."""
        pkgs = [p for p in pkgs if p]
        if not pkgs:
            return []
        cmd = "pacman -T " + " ".join(shlex.quote(p) for p in pkgs)
        try:
            out = subprocess.check_output(["bash", "-lc", cmd], text=True, stderr=subprocess.DEVNULL)
            return [ln.strip() for ln in out.splitlines() if ln.strip()]
        except subprocess.CalledProcessError as e:
            text = (e.output or "")
            return [ln.strip() for ln in text.splitlines() if ln.strip()]
        except Exception:
            missing = []
            for p in pkgs:
                rc = subprocess.run(["bash","-lc",f"pacman -Q {shlex.quote(p)} >/dev/null 2>&1"]).returncode
                if rc != 0:
                    missing.append(p)
            return missing

    def _any_installed(self, pkgs: Sequence[str]) -> bool:
        """Retorna True se qualquer pacote da lista já estiver instalado."""
        pkgs = [p for p in pkgs if p]
        if not pkgs:
            return False
        missing = set(self._missing_packages(pkgs))
        return len(missing) < len(set(pkgs))

    def _split_official_aur(self, pkgs: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Separa pacotes entre oficiais e AUR."""
        pkgs = list(pkgs)
        official_set = _which_in_official_repos(pkgs)
        official, aur = [], []
        for p in pkgs:
            (official if p in official_set else aur).append(p)
        return official, aur

    def _detect_initramfs_tool(self) -> Tuple[str, str]:
        """Detecta ferramenta de initramfs e comando para regenerar."""
        if shutil.which("mkinitcpio"):
            return "mkinitcpio", "mkinitcpio -P"
        if shutil.which("dracut"):
            return "dracut", "dracut -f --kver \"$(uname -r)\""
        return "mkinitcpio", "mkinitcpio -P"

    # ---------- Polkit Policy ----------
    def _ensure_polkit_policy(self) -> None:
        """Garante a presença da policy e wrapper runroot (idempotente)."""
        policy_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <action id="{RUNROOT_POLICY_ID}">
    <description>{T("Executar tarefas administrativas do GNU/Shark")}</description>
    <message>{T("Permitir que o GNU Shark execute ações com privilégios administrativas?")}</message>
    <icon_name>applications-games</icon_name>
    <defaults>
      <allow_any>auth_admin_keep</allow_any>
      <allow_inactive>auth_admin_keep</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{RUNROOT_WRAPPER_PATH}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
""".strip("\n")
        wrapper_content = """#!/bin/sh
# Wrapper minimalista para execução root via polkit
umask 022
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset BASH_ENV ENV
exec /usr/bin/bash -s
""".strip("\n")

        script = f"""set -euo pipefail
run_root_sh <<'EOS'
mkdir -p /usr/share/polkit-1/actions
mkdir -p /usr/libexec
cat > {shlex.quote(RUNROOT_WRAPPER_PATH)} <<'EOF'
{wrapper_content}
EOF
chmod 0755 {shlex.quote(RUNROOT_WRAPPER_PATH)}
chown root:root {shlex.quote(RUNROOT_WRAPPER_PATH)} || true
cat > {shlex.quote(RUNROOT_POLICY_PATH)} <<'EOF'
{policy_content}
EOF
chmod 0644 {shlex.quote(RUNROOT_POLICY_PATH)} || true
EOS
"""
        if getattr(self, "_policy_installing", False):
            return
        with self._policy_lock:
            self._policy_installing = True
            try:
                check_cmd = f"""
[ -f {shlex.quote(RUNROOT_POLICY_PATH)} ] && [ -x {shlex.quote(RUNROOT_WRAPPER_PATH)} ] && \
cmp -s {shlex.quote(RUNROOT_WRAPPER_PATH)} <(cat <<'EOF'
{wrapper_content}
EOF
) && cmp -s {shlex.quote(RUNROOT_POLICY_PATH)} <(cat <<'EOF'
{policy_content}
EOF
)
"""
                if subprocess.run(["bash","-lc",check_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    return
                self._open_terminal_and_run_pipeline(script, need_root=True, ensure_policy=False)
            finally:
                self._policy_installing = False

    # ---------- Execução em terminal/headless ----------
    def _open_terminal_and_run_pipeline(self, bash_script: str, need_root: bool = False, ensure_policy: bool = True) -> bool:
        """
        Abre terminal (preferindo Wayland-friendly) e executa o pipeline.
        Define helpers run_root/run_root_sh no subshell.
        Cai para modo headless (log em /tmp) se nenhum terminal for encontrado.
        Exibe 'Processo finalizado' apenas quando a sentinela é criada ao final do script.
        """
        # Detecta modo de elevação
        run_mode = "user"
        if need_root:
            if os.geteuid() == 0:
                run_mode = "root-euid0"
            elif shutil.which("pkexec"):
                run_mode = "root-pkexec"
            else:
                run_mode = "root-sudo"

        # Helpers run_root
        if need_root and os.geteuid() == 0:
            run_root_def = r"""
run_root() { env PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" bash -lc "$1"; }
run_root_sh() { env PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" bash -lc "$(cat)"; }
export -f run_root run_root_sh
""".strip()
        elif need_root and shutil.which("pkexec"):
            if ensure_policy and not getattr(self, "_policy_installing", False):
                self._ensure_polkit_policy()
            run_root_def = fr"""
run_root() {{ printf '%s\n' "$1" | pkexec {RUNROOT_WRAPPER_PATH}; }}
run_root_sh() {{ pkexec {RUNROOT_WRAPPER_PATH}; }}
export -f run_root run_root_sh
""".strip()
        elif need_root:
            # Suporte a askpass gráfico quando SUDO_ASKPASS estiver definido
            askpass = os.environ.get("SUDO_ASKPASS", "")
            sudo_flags = "-A -k" if askpass else "-k"
            if not shutil.which("pkexec") and not askpass:
                LOG.info("SUDO_ASKPASS não definido; será usado sudo no terminal interativo.")
            run_root_def = f"""
run_root() {{ sudo {sudo_flags} bash -lc "$1"; }}
run_root_sh() {{ sudo {sudo_flags} bash -lc "$(cat)"; }}
export -f run_root run_root_sh
""".strip()
        else:
            run_root_def = r"""
run_root() { bash -lc "$1"; }
run_root_sh() { bash -lc "$(cat)"; }
export -f run_root run_root_sh
""".strip()

        # Script completo + sentinela final
        sentinel_path = f"/tmp/gnusk_done_{os.getpid()}_{int(time.time()*1000)}"
        prefix = ["set -e", EXPECT_FUNC, run_root_def]
        full_script = (
            " ; ".join(prefix)
            + " ; set -o pipefail ; "
            + bash_script
            + f" ; printf DONE > {shlex.quote(sentinel_path)} ; sync ; true"
        )

        def _terminal_cmd_for(name: str) -> Optional[Tuple[List[str], bool]]:
            """Retorna comando base do terminal pré-configurado pelo nome."""
            for t in TERMINALS:
                if t.name == name and shutil.which(t.name):  # FIX: usar t.name aqui
                    return (list(t.args), bool(t.needs_string))
            return None

        argv: Optional[List[str]] = None
        term_env = os.environ.get("TERMINAL")

        if term_env:
            found = _terminal_cmd_for(term_env)
            if found:
                base, needs_string = found
                argv = base + ([f"bash -lc {shlex.quote(full_script)}"] if needs_string else [full_script])

        if argv is None:
            wayland = os.environ.get("XDG_SESSION_TYPE","").lower() == "wayland"
            terms = sorted(TERMINALS, key=lambda t: not t.wayland_pref) if wayland else TERMINALS
            for t in terms:
                if shutil.which(t.name):
                    base = list(t.args)
                    argv = base + ([f"bash -lc {shlex.quote(full_script)}"] if t.needs_string else [full_script])
                    break

        # Sem terminal → modo headless com log
        if argv is None:
            def worker_headless() -> None:
                with tempfile.NamedTemporaryFile(prefix="gnusk_headless_", suffix=".log",
                                                 delete=False, mode="w", encoding="utf-8") as logf:
                    log_path = Path(logf.name)
                    try:
                        proc = subprocess.Popen(["bash","-lc",full_script], stdout=logf, stderr=subprocess.STDOUT)
                        proc.wait()
                        def done_msg() -> None:
                            dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                                    message_type=Gtk.MessageType.INFO,
                                                    buttons=Gtk.ButtonsType.OK,
                                                    text=T("Concluído (modo sem terminal)"),
                                                    use_header_bar=False)
                            dlg.set_default_size(420, 200); dlg.set_size_request(420, 200)
                            dlg.format_secondary_text(T("Execução finalizada.\nLog salvo em: {log_path}\n\nVocê pode abrir o arquivo de log para detalhes.", log_path=str(log_path)))
                            dlg.show_all()
                            dlg.run()
                            dlg.destroy()
                        GLib.idle_add(done_msg)
                    except Exception as e:
                        GLib.idle_add(self._error, T("Falha na execução"), str(e))
            threading.Thread(target=worker_headless, daemon=True).start()
            return True

        # Se vamos usar sudo no terminal, minimizar app para não ficar na frente
        if run_mode == "root-sudo":
            try:
                GLib.idle_add(self.iconify)
            except Exception:
                pass

        def worker() -> None:
            try:
                subprocess.Popen(argv)
                # Espera a sentinela em outra thread (não bloqueia aqui)
                threading.Thread(
                    target=self._wait_sentinel_then_notify,
                    args=(sentinel_path, run_mode == "root-sudo"),
                    daemon=True
                ).start()
            except Exception as e:
                GLib.idle_add(self._error, T("Falha na execução"), str(e))

        threading.Thread(target=worker, daemon=True).start()
        return True

    # ---------- Construção de scripts ----------
    def _build_install_script(self, official: Sequence[str], aur: Sequence[str]) -> Optional[str]:
        """Constroi pipeline de instalação combinando oficiais + AUR quando necessário."""
        mgr = self.pkg_manager or pick_pkg_manager()
        if not mgr:
            return None
        lines = ["set -euo pipefail"]
        if official:
            pkgs = " ".join(shlex.quote(p) for p in official)
            if mgr == "pamac":
                lines.append(f"expect_yes_pac \"run_root \\\"pamac install {pkgs}\\\"\"")
            else:
                lines.append(f"expect_yes_pac \"run_root \\\"pacman -S --needed {pkgs}\\\"\"")
        if aur:
            aur_pkgs = " ".join(shlex.quote(p) for p in aur)
            helper = mgr if mgr in ("paru","yay") else ("paru" if shutil.which("paru") else "yay" if shutil.which("yay") else None)
            if helper:
                if helper == "paru":
                    # sem review/edição e sem prompts extras
                    lines.append(f"{helper} -S --needed --skipreview --noconfirm {aur_pkgs}")
                else:  # yay
                    lines.append(f"{helper} -S --needed --noconfirm --answerdiff None --answeredit None {aur_pkgs}")
            elif mgr == "pamac":
                lines.append(f"expect_yes_pac \"pamac build --no-confirm {aur_pkgs}\"")
            else:
                return None
        return " ; ".join(lines)

    def _kernel_variant(self) -> str:
        """Retorna a variante do kernel (uname -r) em minúsculas."""
        try:
            return subprocess.check_output(["uname","-r"], text=True).strip().lower()
        except Exception:
            return ""

    def _header_pkg_candidates(self) -> List[str]:
        """Retorna candidatos plausíveis de headers para o kernel atual."""
        ver = self._kernel_variant(); cands: List[str] = []
        if "-zen" in ver: cands.append("linux-zen-headers")
        if "-lts" in ver: cands.append("linux-lts-headers")
        if "-hardened" in ver: cands.append("linux-hardened-headers")
        if "-cachyos" in ver: cands.append("linux-cachyos-headers")
        try:
            out = subprocess.check_output(
                ["bash","-lc","pacman -Qq | grep -E '^(linux([0-9]+)?(-[a-z0-9]+)*)$' | grep -v -- '-headers$' || true"], text=True)
            for line in out.splitlines():
                base = line.strip()
                if base and base.startswith("linux"):
                    cands.append(f"{base}-headers")
        except Exception:
            pass
        cands.append("linux-headers")
        try:
            out = subprocess.check_output(["bash","-lc","pacman -Qq | grep -E '^linux.*-headers$' || true"], text=True)
            for line in out.splitlines():
                pkg = line.strip()
                if pkg: cands.append(pkg)
        except Exception:
            pass
        seen: set = set(); ordered: List[str] = []
        for p in cands:
            if p not in seen:
                seen.add(p); ordered.append(p)
        return ordered

    def _matching_header_pkg(self) -> Optional[str]:
        """Tenta casar headers com a variante do kernel atual; fallback para existentes no repo."""
        ver = self._kernel_variant()
        cands = self._header_pkg_candidates()
        for p in cands:
            if "-zen" in ver and p.startswith("linux-zen-headers"): return p
            if "-lts" in ver and p.startswith("linux-lts-headers"): return p
            if "-hardened" in ver and p.startswith("linux-hardened-headers"): return p
            if "-cachyos" in ver and p.startswith("linux-cachyos-headers"): return p
        for p in cands:
            if subprocess.run(["bash","-lc",f"pacman -Si {shlex.quote(p)} >/dev/null 2>&1"]).returncode == 0:
                return p
        return None

    def _headers_installed(self) -> bool:
        """True se algum pacote de headers compatível já estiver instalado."""
        exact = self._matching_header_pkg()
        if exact:
            if subprocess.run(["bash","-lc",f"pacman -Q {shlex_quote(exact)} >/dev/null 2>&1"]).returncode == 0:
                return True
        return any(subprocess.run(["bash","-lc",f"pacman -Q {shlex_quote(p)} >/dev/null 2>&1"]).returncode == 0
                   for p in self._header_pkg_candidates())

    def _multilib_enabled(self) -> bool:
        """True se o repo multilib estiver ativo."""
        try:
            rc = subprocess.run(["bash", "-lc", "pacman -Sl multilib >/dev/null 2>&1"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode
            return rc == 0
        except Exception:
            return False

    # ------------------- Pós-instalação -----------------------
    def _post_gamemode(self) -> None:
        cmd = "set -euo pipefail ; systemctl --user enable --now gamemoded || true ; gamemoded -t || true"
        def worker() -> None:
            try:
                out = subprocess.check_output(["bash","-lc",cmd], text=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                out = e.output or str(e)
            GLib.idle_add(self._info, T("GameMode"), T("Serviço ativado.\n\nResultado do teste:\n{out}", out=out.strip()))
        threading.Thread(target=worker, daemon=True).start()

    def _post_cpupower(self) -> None:
        script_body = r"""
echo governor=\"performance\" > /etc/default/cpupower
systemctl enable --now cpupower || true
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors 2>/dev/null | tr " " "\n" | grep -E "^(performance|schedutil)$" | head -n1)
[ -z "$GOV" ] && GOV=performance
for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo $GOV > "$f" 2>/dev/null || true; done
"""
        self._open_terminal_and_run_pipeline(
            " ; ".join(["set -euo pipefail","run_root_sh <<'EOS'\n"+script_body+"EOS"]),
            need_root=True
        )

    def _post_zram(self) -> None:
        size_str, comp, swappiness = self._choose_zram_params()
        cfg_block = "\n".join([
            "[zram0]",
            f"zram-size = {size_str}",
            f"compression-algorithm = {comp}",
            "swap-priority = 100",
        ])
        sysctl_block = f"vm.swappiness = {swappiness}\n"
        script = f"""set -euo pipefail
run_root_sh <<'EOS'
mkdir -p /etc/systemd
cat > /etc/systemd/zram-generator.conf <<'EOF'
{cfg_block}
EOF
mkdir -p /etc/sysctl.d
cat > /etc/sysctl.d/99-zram-tuning.conf <<'EOF'
{sysctl_block}
EOF
systemctl daemon-reload || true
sysctl --system >/dev/null 2>&1 || true
systemctl start zram0.swap || systemctl start /dev/zram0.swap || true
swapon -a || true
EOS
"""
        self._open_terminal_and_run_pipeline(script, need_root=True)
        swapon_out = _run_cmd_get_output("swapon --show || true").strip() or "(sem saída de swapon --show)"
        self._info(
            T("zram configurado"),
            T("ZRAM ajustado automaticamente:") + "\n"
            + T("• Tamanho:") + f" {size_str}\n"
            + T("• Compressão:") + f" {comp}\n"
            + T("• vm.swappiness:") + f" {swappiness}\n\n"
            + T("Estado atual (swapon --show):") + f"\n{swapon_out}"
        )

    def _post_tuned(self) -> None:
        self._open_terminal_and_run_pipeline(
            "set -euo pipefail ; run_root 'systemctl enable --now tuned || true' ; run_root 'tuned-adm profile latency-performance || true'",
            need_root=True
        )

    def _post_preload(self) -> None:
        self._open_terminal_and_run_pipeline("set -euo pipefail ; run_root 'systemctl enable --now preload || true'", need_root=True)

    POST_STEPS: Dict[str, Callable[[], None]] = {}
    def _init_post_steps(self) -> None:
        """Inicializa mapa de pós-steps por item id."""
        self.POST_STEPS = {
            "zram": self._post_zram,
            "cpupower-performance": self._post_cpupower,
            "gamemode": self._post_gamemode,
            "tuned-performance": self._post_tuned,
            "preload": self._post_preload,
        }

    # ------------------- Flatpak -----------------------
    def _flatpak_available(self) -> bool:
        return shutil.which("flatpak") is not None

    def _flathub_remote_present(self) -> bool:
        """Retorna True se o remote 'flathub' já estiver configurado."""
        try:
            cmd = "flatpak remotes --columns=name | grep -qx flathub"
            return subprocess.run(["bash","-lc",cmd],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,
                                  check=False).returncode == 0
        except Exception:
            return False

    def _ensure_flathub(self) -> bool:
        """
        (Uso geral) Garante que o remote 'flathub' exista, sem diálogos.
        Mantido simples para não interferir nos outros cards.
        """
        if not self._flatpak_available():
            return False
        if not self._flathub_remote_present():
            self._open_terminal_and_run_pipeline(
                "set -euo pipefail; flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo",
                need_root=False
            )
        return True

    def _flatpak_install_script(self, app_id: str) -> str:
        """Monta comando de instalação via flatpak (flathub)."""
        return f"set -euo pipefail; flatpak install -y --or-update flathub {shlex_quote(app_id)}"

    def _flatpak_is_installed(self, app_id: str) -> bool:
        """True se app-id já estiver instalado no flatpak."""
        try:
            cmd = f"flatpak list --app --columns=application | grep -Fxq {shlex_quote(app_id)}"
            return subprocess.run(["bash","-lc", cmd],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,
                                  check=False).returncode == 0
        except Exception:
            return False

    def _open_flatpak_app(self, app_id: str) -> None:
        """Tenta executar um aplicativo flatpak pelo app-id."""
        try:
            subprocess.Popen(["flatpak","run",app_id])
        except Exception as e:
            self._error(T("Falha ao abrir"), T("Não foi possível iniciar '{exe}'.\n\n{e}", exe=app_id, e=str(e)))

    def _kernel_module_vendors(self) -> List[str]:
        return _gpu_modules_present()

    # ------------------- Regras de compatibilidade (GPU/CPU) -------------------
    def _block_incompatible(self, item_id: str, label: str) -> bool:
        """Valida compatibilidade de hardware básica e mostra erro se necessário."""
        vendors = set(self.gpu_vendors or detect_gpu_vendors())
        vendors |= set(self._kernel_module_vendors())
        cpu = (self.cpu_vendor or detect_cpu_vendor()) or "desconhecido"

        def show(msg: str) -> None:
            self._error(T("Hardware incompatível"), T(msg))

        if item_id == "nvidia-driver":
            if "nvidia" not in vendors:
                show("Não detectei GPU NVIDIA neste sistema. Instalação do driver NVIDIA foi bloqueada.")
                return True
        if item_id == "intel-mesa":
            if "intel" not in vendors:
                if cpu == "amd":
                    show("Processador AMD detectado e nenhuma GPU Intel identificada. Instalação de drivers Intel foi bloqueada.")
                else:
                    show("Não detectei GPU Intel neste sistema. Instalação de drivers Intel foi bloqueada.")
                return True
        if item_id == "amd-mesa":
            if "amd" not in vendors:
                show("Não detectei GPU AMD neste sistema. Instalação de drivers AMD foi bloqueada.")
                return True
        return False

    # ------------------- AUR helper (automático) -------------------
    def _ensure_aur_helper_auto(self) -> Optional[str]:
        """Garante a presença de um helper AUR (paru/yay) quando necessário."""
        for helper in ("paru", "yay"):
            if shutil.which(helper):
                return helper
        # Tentativas via pacman (se disponível)
        for helper in ("paru", "yay"):
            if subprocess.run(["bash","-lc",f"pacman -Si {shlex_quote(helper)} >/dev/null 2>&1"]).returncode == 0:
                script = f"expect_yes_pac \"run_root \\\"pacman -S --needed {shlex_quote(helper)}\\\"\""
                self._open_terminal_and_run_pipeline(script, need_root=True)
                self._info(T("AUR"), T("Instalação de {cand} iniciada. Assim que concluir, volte e tente novamente.", cand=helper))
                return None
        # Se houver pamac, tentar build do paru
        if shutil.which("pamac"):
            helper = "paru"
            script = f"expect_yes_pac \"run_root \\\"pamac build --no-confirm {shlex_quote(helper)}\\\"\""
            self._open_terminal_and_run_pipeline(script, need_root=True)
            self._info(T("AUR"), T("Instalação de {cand} iniciada. Assim que concluir, volte e tente novamente.", cand=helper))
            return None
        return None

    # ------------------- ZRAM parâmetros -------------------
    def _detect_total_ram_mib(self) -> int:
        try:
            txt = Path("/proc/meminfo").read_text()
            for line in txt.splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
        except Exception:
            pass
        try:
            out = subprocess.check_output(["bash","-lc","free -m | awk '/^Mem:/{print $2}'"], text=True)
            return int(out.strip())
        except Exception:
            return 4096

    def _detect_cpu_count(self) -> int:
        try:
            out = subprocess.check_output(["bash","-lc","nproc"], text=True)
            c = int(out.strip())
            return c if c > 0 else 1
        except Exception:
            return os.cpu_count() or 1

    def _choose_zram_params(self) -> Tuple[str, str, int]:
        """Escolhe parâmetros de zram com base em RAM total e #CPUs."""
        ram_mib = self._detect_total_ram_mib()
        cores = self._detect_cpu_count()
        if ram_mib <= 4096:
            size_mib = ram_mib
        elif ram_mib <= 8192:
            size_mib = int(ram_mib * 0.75)
        elif ram_mib <= 16384:
            size_mib = ram_mib // 2
        elif ram_mib <= 65536:
            size_mib = 8192
        else:
            size_mib = 16384
        size_mib = max(256, (size_mib // 256) * 256)
        size_str = f"{size_mib // 1024}G" if size_mib % 1024 == 0 else f"{size_mib}M"
        comp = "lzo-rle" if cores <= 2 else ("lz4" if cores <= 8 else "zstd")
        swap = 100 if ram_mib <= 8192 else (80 if ram_mib <= 16384 else 60)
        return size_str, comp, swap

    # ------------------- Fluxo ESPECÍFICO do card Flathub (submenu Repositórios) -------------------
    def _flathub_card_flow(self) -> None:
        """
        - Já tem Flatpak+Flathub → mostra 'Flathub Ativo' + texto curto.
        - Tem Flatpak mas sem Flathub → pergunta apenas se quer ativar; OK ativa; Cancelar aborta.
        - Não tem Flatpak → pergunta se quer instalar/ativar e já adicionar Flathub; OK prossegue; Cancelar aborta.
        """
        if self._flatpak_available():
            if self._flathub_remote_present():
                self._info(T("Flathub Ativo"), T("O suporte a flatpak já está habilitado em seu sistema."))
                return
            if not self._confirm(T("Configuração do Flathub"),
                                 T("Ativar o repositório Flathub agora?")):
                return
            self._open_terminal_and_run_pipeline(
                "set -euo pipefail; flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo",
                need_root=False
            )
            self._info(T("Flathub Ativo"), T("O suporte a flatpak já está habilitado em seu sistema."))
            return
        # Flatpak ausente
        if not self._confirm(T("Configuração do Flatpak"),
                             T("Ativar o suporte a Flatpak e adicionar o repositório Flathub agora?")):
            return
        script_install = self._build_install_script(["flatpak"], [])
        if not script_install:
            self._error(T("Instalação"), T("Não foi possível construir o script de instalação (helper AUR ausente?)."))
            return
        full = " ; ".join([
            script_install,
            "flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo || true",
        ])
        self._open_terminal_and_run_pipeline(full, need_root=True)
        self._info(T("Flathub Ativo"), T("O suporte a flatpak já está habilitado em seu sistema."))

    # ------------------- Fluxo principal de ação -------------------
    def handle_action(self, section_key: str, item: Dict[str, str]) -> None:  # noqa: ARG002
        """
        Fluxo de clique em item:
          - Bloqueios por compatibilidade
          - NVIDIA: seleção de pacotes + headers quando necessário
          - Multilib assistido
          - Instalação do que falta usando prioridade Repo > Flatpak > AUR
          - Pós-steps específicos por item
        """
        # Card dedicado do Flathub (apenas no submenu Repositórios)
        if item.get("id") == "flathub":
            self._flathub_card_flow()
            return

        if self._block_incompatible(item["id"], item["label"]):
            return

        # NVIDIA prepara lista de pacotes de acordo com o kernel
        if item["id"] == "nvidia-driver":
            pkgs = self._nvidia_packages()
            cfg = {"packages": pkgs}
            if "nvidia-dkms" in pkgs and not self._ensure_kernel_headers():
                self._info(T("Atenção"), T("Instale os headers do kernel e tente novamente para usar nvidia-dkms."))
                return
        else:
            cfg = ACTION_MAP.get(item["id"], {})

        pkgs: List[str] = list(cfg.get("packages", []))            # type: ignore
        exe: Optional[str] = cfg.get("exec")                       # type: ignore
        flatpak_id: Optional[str] = cfg.get("flatpak")             # type: ignore
        alt_pkgs: List[str] = list(cfg.get("alt_packages", []))    # type: ignore

        # Para o card Wine, considerar que o exec é winecfg
        if item["id"] == "wine":
            exe = "winecfg"

        # --- (NOVO) Anexar prompt do GStreamer ao final da instalação do Wine ---
        def _script_with_optional_gstreamer(base_script: str) -> str:
            """Após instalar Wine, pergunta (zenity/TTY) e instala GStreamer na mesma execução."""
            if item["id"] != "wine":
                return base_script

            gst_missing = self._missing_packages(GSTREAMER_WINE_PKGS)
            if not gst_missing:
                return base_script  # nada a ofertar

            # Preparar instalação (Repo > AUR) dos pacotes que realmente faltam
            official_gst, aur_gst = self._split_official_aur(gst_missing)
            gst_script = self._build_install_script(official_gst, aur_gst)
            if not gst_script:
                return base_script  # sem helper AUR disponível etc.

            pkgs_str = " ".join(gst_missing)
            prompt_title = T("Confirmar")
            prompt_text  = T("Instalar suporte multimídia (GStreamer) para o Wine?")

            ask_block = f"""
# --- Perguntar sobre GStreamer ao final do Wine ---
_do_gst=0
if command -v zenity >/dev/null 2>&1; then
  zenity --question --title="{prompt_title}" --no-wrap --text="{prompt_text}\\n\\nPacotes: {pkgs_str}" && _do_gst=1 || true
else
  printf "\\n{prompt_text}\\nPacotes: {pkgs_str}\\n[y/N]: "
  read -r _ans; case "$_ans" in [yY]|[yY][eE][sS]|[sS]) _do_gst=1;; esac
fi
if [ "$_do_gst" -eq 1 ]; then
  {gst_script}
fi
""".strip("\n")

            return base_script + " ; " + ask_block

        # --------- (NOVO) Gatilho explícito de multilib para apps conhecidos ---------
        requires_multilib = item["id"] in {"steam", "wine", "mangohud"}
        if requires_multilib and not self._multilib_enabled():
            if self._confirm(T("Multilib"),
                             T("Alguns pacotes 32-bit requerem o repositório [multilib].\n\nAtivar automaticamente e atualizar bancos de dados agora?")):
                script = r"""
run_root_sh <<'EOS'
set -euo pipefail
cp /etc/pacman.conf{,.bak.$(date +%F-%H%M%S)}
sed -ri 's/^\s*#\s*\[multilib\]/[multilib]/' /etc/pacman.conf
sed -ri '/^\s*\[multilib\]/,/\s*(\[|\Z)/ { s/^\s*#\s*(Include)/\1/ }' /etc/pacman.conf
grep -q '^\[multilib\]' /etc/pacman.conf
pacman -Syy
EOS
"""
                self._open_terminal_and_run_pipeline(script, need_root=True)
            else:
                self._info(T("Multilib"), T("Ative manualmente em /etc/pacman.conf e rode: sudo pacman -Syy"))
                return

        # Resolver provedores virtuais (evita prompts do AUR)
        pkgs = self._resolve_virtual_pkgs(pkgs)

        # Já instalado? Oferece abrir
        if exe and shutil.which(exe):
            if self._confirm(T("Abrir"), T("Abrir {label} agora?", label=item['label'])):
                try:
                    cli_like = exe in {"steam-acolyte", "paru", "yay"}
                    if cli_like:
                        self._open_terminal_and_run_pipeline(exe, need_root=False, ensure_policy=False)
                    else:
                        subprocess.Popen([exe])
                except Exception as e:
                    self._error(T("Falha ao abrir"), T("Não foi possível iniciar '{exe}'.\n\n{e}", exe=exe, e=str(e)))
            return

        if flatpak_id and self._flatpak_available() and self._flatpak_is_installed(flatpak_id):
            if self._confirm(T("Abrir"), T("Abrir {label} agora?", label=item['label'])):
                self._open_flatpak_app(flatpak_id)
            return

        # Descobre o que falta instalar
        to_install: List[str] = self._missing_packages(pkgs)

        # Se uma alternativa aceita já estiver instalada, não instale nada
        if to_install and alt_pkgs and self._any_installed(alt_pkgs):
            to_install = []

        # Nada a instalar -> para itens com exec (ex.: wine), oferecer abrir
        if not to_install:
            if exe:
                if self._confirm(T("Abrir"), T("Abrir {label} agora?", label=item['label'])):
                    try:
                        subprocess.Popen([exe])
                    except Exception as e:
                        self._error(T("Falha ao abrir"), T("Não foi possível iniciar '{exe}'.\n\n{e}", exe=exe, e=str(e)))
                return
            self._info(T("Nada a instalar"), T("Não há pacotes pendentes para {label}.", label=item["label"]))
            return

        # Multilib (fallback baseado em lib32-*)
        if any(p.startswith("lib32-") for p in to_install) and not self._multilib_enabled():
            if self._confirm(T("Multilib"),
                             T("Alguns pacotes 32-bit requerem o repositório [multilib].\n\nAtivar automaticamente e atualizar bancos de dados agora?")):
                script = r"""
run_root_sh <<'EOS'
set -euo pipefail
cp /etc/pacman.conf{,.bak.$(date +%F-%H%M%S)}
sed -ri 's/^\s*#\s*\[multilib\]/[multilib]/' /etc/pacman.conf
sed -ri '/^\s*\[multilib\]/,/\s*(\[|\Z)/ { s/^\s*#\s*(Include)/\1/ }' /etc/pacman.conf
grep -q '^\[multilib\]' /etc/pacman.conf
pacman -Syy
EOS
"""
                self._open_terminal_and_run_pipeline(script, need_root=True)
            else:
                self._info(T("Multilib"), T("Ative manualmente em /etc/pacman.conf e rode: sudo pacman -Syy"))
                return

        # --- Seleção automática da fonte (Repo > Flatpak > AUR) ---
        official, aur = self._split_official_aur(to_install)
        LOG.info("Fonte escolhida para %s → repo=%s, aur=%s, flatpak=%s",
                 item["id"], bool(official), bool(aur), bool(flatpak_id))

        if official:
            need_helper = bool(aur) and (self.pkg_manager not in ("paru","yay","pamac")) and not (shutil.which("paru") or shutil.which("yay"))
            if need_helper:
                helper = self._ensure_aur_helper_auto()
                if helper is None and self.pkg_manager != "pamac":
                    self._error(T("AUR helper ausente"), T("Instalação abortada por falta de helper AUR."))
                    return
            script = self._build_install_script(official, aur)
            if not script:
                self._error(T("Instalação"), T("Não foi possível construir o script de instalação (helper AUR ausente?)."))
                return
            # se for o Wine, anexar pergunta do GStreamer só no final
            script = _script_with_optional_gstreamer(script)
            pkgs_str = " ".join(to_install)
            if not self._confirm(T("Confirmar"), T("Instalar {pkgs_str}?", pkgs_str=pkgs_str)):
                return
            self._open_terminal_and_run_pipeline(script, need_root=True)

        elif flatpak_id and self._flatpak_available():
            # Garante o remote e instala
            script = f"set -euo pipefail; flatpak install -y --or-update flathub {shlex_quote(flatpak_id)}"
            self._ensure_flathub()
            if not self._confirm(T("Confirmar"),
                                 T("Instalar {label} via Flatpak?", label=item['label'])):
                return
            self._open_terminal_and_run_pipeline(script, need_root=False)

        else:
            # Tentar somente AUR
            need_helper = (self.pkg_manager not in ("paru","yay","pamac")) and not (shutil.which("paru") or shutil.which("yay"))
            if need_helper:
                helper = self._ensure_aur_helper_auto()
                if helper is None and self.pkg_manager != "pamac":
                    self._error(T("AUR helper ausente"), T("Instalação abortada por falta de helper AUR."))
                    return
            script = self._build_install_script([], aur=to_install)
            if not script:
                self._error(T("Instalação"), T("Não foi possível construir o script de instalação (helper AUR ausente?)."))
                return
            # se for o Wine, anexar pergunta do GStreamer só no final
            script = _script_with_optional_gstreamer(script)
            pkgs_str = " ".join(to_install)
            if not self._confirm(T("Confirmar"), T("Instalar {pkgs_str}?", pkgs_str=pkgs_str)):
                return
            self._open_terminal_and_run_pipeline(script, need_root=True)

        # Pós-steps (best-effort)
        post = self.POST_STEPS.get(item["id"])
        if post:
            try:
                post()
            except Exception as e:
                GLib.idle_add(self._error, T("Falha na execução"), str(e))

        # NVIDIA: initramfs + reboot (opcional)
        if item["id"] == "nvidia-driver" and self._nvidia_loaded():
            tool, cmd = self._detect_initramfs_tool()
            if self._confirm(T("NVIDIA: regenerar initramfs"), T("Detectei o driver NVIDIA carregado.\nRegenerar initramfs agora com {tool}?", tool=tool)):
                self._open_terminal_and_run_pipeline(f"run_root '{cmd}'", need_root=True)
                if self._confirm(T("Reiniciar"), T("Reiniciar o sistema agora?")):
                    self._open_terminal_and_run_pipeline("run_root 'reboot'", need_root=True)

    # ------------------- Diálogos básicos -------------------
    def _confirm(self, title: str, primary: str, secondary: Optional[str] = None) -> bool:
        """Caixa de pergunta padrão (OK/Cancelar)."""
        dlg = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=T(title),
            use_header_bar=False,
        )
        dlg.set_default_size(420, 200); dlg.set_size_request(420, 200)
        dlg.format_secondary_text(T(primary) + (("\n\n" + T(secondary)) if secondary else ""))
        for ch in dlg.get_message_area().get_children():
            if isinstance(ch, Gtk.Label):
                ch.set_xalign(0.5); ch.set_justify(Gtk.Justification.CENTER)
        dlg.set_default_response(Gtk.ResponseType.OK)
        resp = dlg.run(); dlg.destroy()
        return resp == Gtk.ResponseType.OK

    def _info(self, title: str, text: str) -> None:
        """Caixa de informação padrão (OK)."""
        dlg = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=T(title),
            use_header_bar=False,
        )
        dlg.set_default_size(420, 200); dlg.set_size_request(420, 200)
        dlg.format_secondary_text(T(text))
        for ch in dlg.get_message_area().get_children():
            if isinstance(ch, Gtk.Label):
                ch.set_xalign(0.5); ch.set_justify(Gtk.Justification.CENTER)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.run(); dlg.destroy()

    def _error(self, title: str, text: str) -> None:
        """Caixa de erro padrão (Fechar)."""
        dlg = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=T(title),
            use_header_bar=False,
        )
        dlg.set_default_size(420, 200); dlg.set_size_request(420, 200)
        dlg.format_secondary_text(T(text))
        for ch in dlg.get_message_area().get_children():
            if isinstance(ch, Gtk.Label):
                ch.set_xalign(0.5); ch.set_justify(Gtk.Justification.CENTER)
        dlg.set_default_response(Gtk.ResponseType.CLOSE)
        dlg.run(); dlg.destroy()

    def on_about(self, _btn: Optional[Gtk.Button]) -> None:
        """Diálogo 'Sobre' com logomarca local se disponível."""
        dlg = Gtk.AboutDialog(transient_for=self, modal=True, use_header_bar=False)
        dlg.set_title(T("Sobre")); dlg.set_program_name(APP_TITLE)
        # <<< ALTERADO: inclui a versão no texto e define version do AboutDialog
        dlg.set_comments(f"{T(APP_SUBTITLE)}\n\n" + T("Desenvolvido por Gabriel Ruas Santos"))
        dlg.set_version(APP_VERSION)
        # Preferir ícone local (SVG/PNG) se existir; senão usar nome do tema
        icon_path = find_local_icon_file(APP_ICON_NAME)
        if icon_path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), 128, 128, True)
                dlg.set_logo(pb)
            except Exception:
                dlg.set_logo_icon_name(APP_ICON_NAME)
        else:
            dlg.set_logo_icon_name(APP_ICON_NAME)
        dlg.set_website("https://github.com/gabriel-ruas-santos/gnu-shark.git"); dlg.set_website_label(T("Página do projeto"))
        dlg.set_resizable(False)
        dlg.set_default_response(Gtk.ResponseType.CLOSE)
        dlg.run(); dlg.destroy()

    # ============================
    # Métodos específicos NVIDIA
    # ============================

    def _nvidia_loaded(self) -> bool:
        """True se módulo 'nvidia' estiver carregado."""
        try:
            out = subprocess.check_output(["bash","-lc","lsmod | awk '{print $1}' | grep -x nvidia || true"], text=True)
            return bool(out.strip())
        except Exception:
            return False

    def _ensure_kernel_headers(self) -> bool:
        """
        Garante que headers do kernel estejam instalados.
        Retorna True se já estavam presentes, False se foi disparada instalação e é preciso tentar depois.
        """
        if self._headers_installed():
            return True
        cand = self._matching_header_pkg()
        if not cand:
            return False
        ver = self._kernel_variant()
        LOG.info("Headers de kernel recomendados para %s → %s", ver, cand)
        if self._confirm(T("Headers do kernel"),
                         T("Kernel atual: {ver}\nPara compilar módulos DKMS (ex.: nvidia-dkms) é recomendado instalar {cand}.\n\nInstalar agora?", ver=ver, cand=cand)):
            script = f"expect_yes_pac \"run_root \\\"pacman -S --needed {shlex_quote(cand)}\\\"\""
            self._open_terminal_and_run_pipeline(script, need_root=True)
            self._info(T("Headers do kernel"), T("Instalação de {cand} iniciada. Assim que concluir, volte e tente novamente.", cand=cand))
            return False
        return False

    def _nvidia_packages(self) -> List[str]:
        """Seleciona pacotes NVIDIA recomendados conforme kernel e preferência 'open'."""
        ver = self._kernel_variant()
        pkgs: List[str] = []
        base = ["nvidia-utils", "lib32-nvidia-utils", "vulkan-icd-loader", "lib32-vulkan-icd-loader"]
        pkgs.extend(base)

        # Preferência opcional pelo driver NVIDIA "open" (Turing+), se disponível
        prefer_open = os.environ.get("GNUSK_PREFER_NVIDIA_OPEN", "").lower() in {"1","true","yes","on"}
        if prefer_open:
            open_first = "nvidia-open-dkms" if ("-lts" in ver or "-zen" in ver or "-cachyos" in ver or "-hardened" in ver) else "nvidia-open"
            open_candidates = [open_first]
            if open_first != "nvidia-open-dkms":
                open_candidates.append("nvidia-open-dkms")
            if open_first != "nvidia-open":
                open_candidates.append("nvidia-open")
            for cand in open_candidates:
                try:
                    if _pkg_in_official_repos_cached(cand):
                        pkgs.insert(0, cand)
                        return pkgs
                except Exception:
                    pass

        if "-lts" in ver:
            pkgs.insert(0, "nvidia-lts")
        elif "-zen" in ver or "-cachyos" in ver or "-hardened" in ver:
            pkgs.insert(0, "nvidia-dkms")
        else:
            pkgs.insert(0, "nvidia")
        return pkgs


# =============================================================================
# Utils auxiliares
# =============================================================================

def shlex_quote(s: str) -> str:
    """Alias com type-hint para shlex.quote."""
    return shlex.quote(s)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    """Ponto de entrada da aplicação GTK."""
    _bootstrap_app_identity()  # garante app-id e ícone antes de abrir a janela
    win = App()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

def _print_version_and_exit() -> None:
    """Imprime a versão no CLI e encerra."""
    print(f"{APP_TITLE} {APP_VERSION}")
    sys.exit(0)

if __name__ == "__main__":
    if "--version" in sys.argv:
        _print_version_and_exit()
    main()
