# AUR Packaging for webstat

This directory contains Arch User Repository (AUR) package specifications for `webstat`.

## Packages

- **`webstat-git`**: Tracks the latest git `main` branch from GitHub (VCS package).
- **`webstat`**: Tracks stable tagged releases from GitHub.

## Local Testing (Arch Linux / Omarchy)

You can build and test-install the package locally right now without submitting to AUR:

```bash
cd packaging/aur/webstat-git
makepkg -si
```

This will clone the repo, build the wheel, package it as an Arch package, and install it via `pacman`.

## Submitting to AUR (When registrations reopen)

Once your AUR account is created and your SSH key is uploaded to [https://aur.archlinux.org/account/](https://aur.archlinux.org/account/):

### 1. Initialize the AUR repository
```bash
git clone ssh://aur@aur.archlinux.org/webstat-git.git /tmp/webstat-git-aur
```

### 2. Copy the PKGBUILD and generate .SRCINFO
```bash
cp PKGBUILD /tmp/webstat-git-aur/
cd /tmp/webstat-git-aur
makepkg --printsrcinfo > .SRCINFO
```

### 3. Commit and push
```bash
git add PKGBUILD .SRCINFO
git commit -m "Initial import of webstat-git"
git push origin master
```

Users on Omarchy / Arch can then immediately install via:
```bash
yay -S webstat-git
# or
paru -S webstat-git
```
