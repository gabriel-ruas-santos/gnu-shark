# GNU/Shark

A simple GTK UI to install GPU drivers, performance tweaks, and gaming tools on Arch-based distributions.  
**App ID:** `org.gnushark.GNUShark` • **Binary/CLI:** `python3 path/to/app.py [--version]`

---

## Overview

GNU/Shark is a small control center for Linux gaming. It detects your hardware, guides you to compatible items, and automates safe installation using your system’s available package tools. When possible it prefers **official repositories**, falling back to **Flatpak (Flathub)** and then **AUR**.

> Tip: The UI is minimal and responsive (grid spacing, section headers, heuristic window sizing). All actions run with a safe PATH and, when needed, elevate via **polkit (pkexec)** or `sudo`.

---

## Features

- **I18N (PT/EN)** with a safe fallback and logging of missing keys
- **Smart install source selection:** Official repo ➜ Flatpak ➜ AUR
- **Privilege escalation:** polkit (`pkexec`) or `sudo` with a “safe” PATH
- **Package automation:** robust pacman/pamac integration (auto-yes only where appropriate)
- **Hardware detection:** CPU/GPU checks and **blocking of incompatible items**
- **ZRAM auto‑tuning:** size, compression, and swappiness + current state report
- **Multilib helper:** assisted enablement when required (e.g., `lib32-*`)
- **Consistent UI:** unified grid spacing, titles/subtitles (subtitle 12pt)
- **Window sizing heuristics** based on the desktop work area
- **Dedicated Flathub flow** (Repositories submenu)

### Included items (examples)

Drivers: Intel Mesa, NVIDIA Proprietary, AMD Mesa/RADV  
Optimizations: GameMode, Tuned, cpupower, ZRAM, Preload  
Tools: Steam, Lutris, Heroic, ProtonPlus, Wine, Bottles, MangoHUD, Steam Acolyte  
Extras: GOverlay, Python Steam, CoreCtrl (AMD), GreenWithEnvy (NVIDIA), AdwSteamGtk

---

## Compatibility

Designed for **Arch Linux** and derivatives (e.g., **Manjaro**, **CachyOS**), using whichever of `pacman`, `paru`, `yay`, or `pamac` is available.

---

## Runtime Requirements

- **Python 3.8+**
- **GTK 3** via **PyGObject**
- Standard system tools as needed (`pacman`, `flatpak`, etc.)

### Arch packages you’ll likely want

```bash
sudo pacman -S --needed python python-gobject gtk3 pciutils   flatpak zenity expect  # optional but recommended
```

- `pciutils` is used for GPU detection (`lspci`).
- `zenity` enables nicer confirmation dialogs from shell flows.
- `expect` enables safe auto-yes for specific pacman/pamac prompts.

---

## Getting Started (from source)

1. **Clone** the repository:
   ```bash
   git clone https://github.com/gabriel-ruas-santos/gnu-shark.git
   cd gnu-shark
   ```

2. **Run** the app:
   ```bash
   ./app.py
   ```
   Or:
   ```bash
   python3 app.py
   ```

3. **Check the version** (CLI):
   ```bash
   python3 app.py --version
   ```

> The app will pick the best available terminal and package manager automatically. When root is required, it prefers **pkexec** (polkit); if unavailable, it will fall back to **sudo**.

---

## How installs are chosen

- First, GNU/Shark resolves missing packages and checks what’s in **official repos**.
- If something isn’t in official repos but is available on **Flathub**, it can install via **Flatpak**.
- If still missing, it builds via **AUR** using your available helper (`paru`/`yay`) or **pamac**.
- Multilib is prompted and can be auto‑enabled when required by 32‑bit packages.

---

## Special notes

### NVIDIA headers / DKMS
If you choose the DKMS variant (e.g., on `-zen`, `-lts`, `-hardened`, `-cachyos` kernels), GNU/Shark will recommend installing **kernel headers** first, and can help regenerate **initramfs** afterwards.

### Multilib
Some items (e.g., **Steam**, **Wine**, **MangoHUD**) require `lib32-*` packages. GNU/Shark offers to enable the `[multilib]` repo automatically; you can also do it manually and run `sudo pacman -Syy`.

### Translations
UI language auto‑detects (PT/EN). Unknown strings safely fall back and are logged for easy contribution.

### Flathub
There is a dedicated card under **Repositories** to enable **Flathub** quickly if Flatpak is present (or to install Flatpak first and then add Flathub).

---

## Troubleshooting

- **No terminal found**: the app can run “headless” and write a log under `/tmp/…`; you’ll be offered to open the log.
- **AUR helper missing**: the app can install `paru`/`yay` (or use `pamac build`) when needed, or it will stop with an explanatory message.
- **Hardware blocked**: If your hardware is incompatible with an item (e.g., installing Intel drivers on non‑Intel GPUs), the app will explain why and prevent the action.

---

## Contributing

Translations and item definitions are straightforward to extend. Feel free to open issues or PRs on the project page.

**Project page:** https://github.com/gabriel-ruas-santos/gnu-shark/wiki

---

## Disclaimer

GNU/Shark tries to make safe choices and ask for confirmation before taking impactful actions, but you are still in control. Review prompts carefully, especially when enabling repositories or installing kernel‑level components.

