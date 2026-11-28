#!/bin/bash
# End-to-end rehearsal of the Arch updater (plan Fase 9: F9-13, F9-09).
#
#   arch-update-e2e.sh <old.pkg.tar.zst> <new.pkg.tar.zst> <new-version> <commit>
#
# Runs as root inside a throwaway Arch container (the `arch-package` CI job),
# never on a real machine: it installs and replaces janitor-desktop-bin and
# overwrites the installed update key with a throwaway one generated here.
# No real signing key is involved.
#
# It installs <old>, then drives the REAL helper
# (/usr/lib/janitor-desktop/janitor-update-helper, as installed by the package)
# the way pkexec would, with PKEXEC_UID of an unprivileged user that owns the
# files, and checks every refusal before the one update that must go through.
# What it cannot cover: the polkit dialog itself (no session, no agent) and the
# systemd-run path (no systemd in the container).

set -euo pipefail

[ "$EUID" -eq 0 ] || { echo "run as root in a throwaway Arch container" >&2; exit 2; }
[ -f /.dockerenv ] || [ -n "${GITHUB_ACTIONS:-}" ] || [ -n "${JANITOR_E2E_CONTAINER:-}" ] \
  || { echo "refusing to run outside a container (it replaces the installed janitor-desktop-bin)" >&2; exit 2; }
[ "$#" -eq 4 ] || { echo "usage: $0 <old.pkg.tar.zst> <new.pkg.tar.zst> <new-version> <commit>" >&2; exit 2; }

OLD_PKG="$(readlink -f "$1")" NEW_PKG="$(readlink -f "$2")" NEW_VERSION="$3" COMMIT="$4"
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER=/usr/lib/janitor-desktop/janitor-update-helper
KEY=/usr/lib/janitor-desktop/update-key.pem
PKG=janitor-desktop-bin

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
installed() { pacman -Q "$PKG" | cut -d' ' -f2; }

say "install the old package"
pacman -U --noconfirm --noprogressbar "$OLD_PKG" >/dev/null
OLD_VERSION="$(installed)"
test -x "$HELPER"
test "$(stat -c '%U %a' "$HELPER")" = "root 755"
test "$(stat -c '%U %a' /var/cache/janitor-desktop)" = "root 700"
test -f /usr/share/polkit-1/actions/ai.janitor.desktop.update.policy
echo "installed: $OLD_VERSION"

id janitor-e2e >/dev/null 2>&1 || useradd --create-home janitor-e2e
USER_UID="$(id -u janitor-e2e)"
HOME_DIR="$(getent passwd janitor-e2e | cut -d: -f6)"
WORK="$HOME_DIR/descarga"
rm -rf "$WORK" && mkdir -p "$WORK/keys" "$WORK/otra" "$WORK/vieja"

say "throwaway keys and signed manifests"
node "$SCRIPTS/update-manifest.mjs" keygen --out "$WORK/keys" >/dev/null
node "$SCRIPTS/update-manifest.mjs" keygen --out "$WORK/otra" >/dev/null
NEW_NAME="$(basename "$NEW_PKG")" OLD_NAME="$(basename "$OLD_PKG")"
cp "$NEW_PKG" "$WORK/$NEW_NAME"
cp "$OLD_PKG" "$WORK/vieja/$OLD_NAME"
node "$SCRIPTS/update-manifest.mjs" build --version "$NEW_VERSION" --commit "$COMMIT" --out "$WORK" "$WORK/$NEW_NAME" >/dev/null
JANITOR_E2E_KEY="$(cat "$WORK/keys/test-update-key.private.pem")" \
  node "$SCRIPTS/update-manifest.mjs" sign --manifest "$WORK/janitor-update.json" --key-env JANITOR_E2E_KEY >/dev/null
# The same manifest signed by a key the package does not trust.
cp "$WORK/janitor-update.json" "$WORK/otra/janitor-update.json"
JANITOR_E2E_KEY="$(cat "$WORK/otra/test-update-key.private.pem")" \
  node "$SCRIPTS/update-manifest.mjs" sign --manifest "$WORK/otra/janitor-update.json" --key-env JANITOR_E2E_KEY >/dev/null
chown -R janitor-e2e: "$WORK"

MANIFEST="$WORK/janitor-update.json" SIG="$WORK/janitor-update.json.sig"

# run <expected exit code> <what> <args…>: the helper as pkexec would start it.
run() {
  local want="$1" what="$2" got=0
  shift 2
  env -i PATH=/usr/bin PKEXEC_UID="${PKEXEC_UID_OVERRIDE-$USER_UID}" "$HELPER" "$@" 2>"$WORK/../stderr.txt" || got=$?
  sed 's/^/    /' "$WORK/../stderr.txt"
  [ "$got" -eq "$want" ] || fail "$what: exit $got, expected $want"
  echo "ok: $what (exit $got)"
}
unchanged() { [ "$(installed)" = "$OLD_VERSION" ] || fail "$1 changed the installed package to $(installed)"; }
clean() { [ -z "$(find /var/cache/janitor-desktop -mindepth 1 -name 'update.*')" ] || fail "the private folder was not cleaned"; }

say "a package built without a release key refuses to update"
: > "$KEY"
run 12 "empty key" "$WORK/$NEW_NAME" "$MANIFEST" "$SIG"
unchanged "an empty key"

install -m 0644 -o root -g root "$WORK/keys/test-update-key.pem" "$KEY"

say "refusals: nothing may change"
PKEXEC_UID_OVERRIDE="" run 10 "not started by pkexec" "$WORK/$NEW_NAME" "$MANIFEST" "$SIG"
run 10 "relative path" "descarga/$NEW_NAME" "$MANIFEST" "$SIG"
cp "$WORK/$NEW_NAME" "$WORK/otro-nombre.pkg.tar.zst"
run 10 "a file that is not named like the Janitor package" "$WORK/otro-nombre.pkg.tar.zst" "$MANIFEST" "$SIG"
run 12 "manifest signed with another key" "$WORK/$NEW_NAME" "$WORK/otra/janitor-update.json" "$WORK/otra/janitor-update.json.sig"
sed 's/"sequence": /"sequence": 1/' "$MANIFEST" > "$WORK/alterado.json" && chown janitor-e2e: "$WORK/alterado.json"
run 12 "manifest altered after signing" "$WORK/$NEW_NAME" "$WORK/alterado.json" "$SIG"

# Validly signed manifests that do not describe this package exactly once.
mkdir -p "$WORK/ajeno" "$WORK/doble"
echo "otro archivo" > "$WORK/ajeno/otro.txt"
node "$SCRIPTS/update-manifest.mjs" build --version "$NEW_VERSION" --commit "$COMMIT" --out "$WORK/ajeno" "$WORK/ajeno/otro.txt" >/dev/null
sed -E 's/^(    \{"name": .*\})$/\1,\n\1/' "$MANIFEST" > "$WORK/doble/janitor-update.json"
[ "$(grep -c '"name": ' "$WORK/doble/janitor-update.json")" -eq 2 ] || fail "the duplicated manifest was not built"
for dir in ajeno doble; do
  JANITOR_E2E_KEY="$(cat "$WORK/keys/test-update-key.private.pem")" \
    node "$SCRIPTS/update-manifest.mjs" sign --manifest "$WORK/$dir/janitor-update.json" --key-env JANITOR_E2E_KEY >/dev/null
done
chown -R janitor-e2e: "$WORK/ajeno" "$WORK/doble"
run 13 "signed manifest without this package" "$WORK/$NEW_NAME" "$WORK/ajeno/janitor-update.json" "$WORK/ajeno/janitor-update.json.sig"
run 13 "signed manifest that lists this package twice" "$WORK/$NEW_NAME" "$WORK/doble/janitor-update.json" "$WORK/doble/janitor-update.json.sig"

# The package the app verified is swapped for another one before root reads it.
mkdir -p "$WORK/sustituido"
head -c "$(stat -c %s "$WORK/$NEW_NAME")" /dev/urandom > "$WORK/sustituido/$NEW_NAME"
chown -R janitor-e2e: "$WORK/sustituido"
run 13 "package replaced after it was verified (same size)" "$WORK/sustituido/$NEW_NAME" "$MANIFEST" "$SIG"
cat "$WORK/$NEW_NAME" "$WORK/$NEW_NAME" > "$WORK/sustituido/$NEW_NAME"
run 11 "package replaced by a bigger file" "$WORK/sustituido/$NEW_NAME" "$MANIFEST" "$SIG"

# Root must not read for the user what the user cannot read.
install -m 0600 -o root -g root "$WORK/$NEW_NAME" /root/"$NEW_NAME"
ln -sf /root/"$NEW_NAME" "$WORK/sustituido/$NEW_NAME"
run 11 "symlink to a file only root can read" "$WORK/sustituido/$NEW_NAME" "$MANIFEST" "$SIG"
rm -f "$WORK/sustituido/$NEW_NAME" && mkfifo "$WORK/sustituido/$NEW_NAME" && chown janitor-e2e: "$WORK/sustituido/$NEW_NAME"
run 11 "a FIFO where the manifest should be" "$WORK/$NEW_NAME" "$WORK/sustituido/$NEW_NAME" "$SIG"
unchanged "a refusal"
clean

# Another update holds the lock.
( flock -n 9 || exit 1; sleep 5 ) 9>/var/cache/janitor-desktop/.lock &
sleep 1
run 17 "another update in progress" "$WORK/$NEW_NAME" "$MANIFEST" "$SIG"
wait
unchanged "a locked-out run"

say "N → N+1"
run 0 "signed update" "$WORK/$NEW_NAME" "$MANIFEST" "$SIG"
NEW_INSTALLED="$(installed)"
[ "$NEW_INSTALLED" != "$OLD_VERSION" ] || fail "the package is still $OLD_VERSION"
[ "$(vercmp "$NEW_INSTALLED" "$OLD_VERSION")" -gt 0 ] || fail "$NEW_INSTALLED is not newer than $OLD_VERSION"
test -x "$HELPER"
test -x /opt/janitor-desktop/Janitor
clean
echo "installed: $NEW_INSTALLED"

say "the same delivery can be repeated; an older one never installs"
install -m 0644 -o root -g root "$WORK/keys/test-update-key.pem" "$KEY"   # the new package brought its own key file
run 0 "same delivery again" "$WORK/$NEW_NAME" "$MANIFEST" "$SIG"
OLD_DISPLAY="${OLD_VERSION%-*}"; OLD_DISPLAY="${OLD_DISPLAY/.janitor./-janitor.}"
node "$SCRIPTS/update-manifest.mjs" build --version "$OLD_DISPLAY" --commit "$COMMIT" --out "$WORK/vieja" "$WORK/vieja/$OLD_NAME" >/dev/null
JANITOR_E2E_KEY="$(cat "$WORK/keys/test-update-key.private.pem")" \
  node "$SCRIPTS/update-manifest.mjs" sign --manifest "$WORK/vieja/janitor-update.json" --key-env JANITOR_E2E_KEY >/dev/null
chown -R janitor-e2e: "$WORK/vieja"
install -m 0644 -o root -g root "$WORK/keys/test-update-key.pem" "$KEY"   # reinstalling replaced it again
run 15 "validly signed but older package" "$WORK/vieja/$OLD_NAME" "$WORK/vieja/janitor-update.json" "$WORK/vieja/janitor-update.json.sig"
[ "$(installed)" = "$NEW_INSTALLED" ] || fail "the package went back to $(installed)"
clean

say "Arch updater e2e: all checks passed ($OLD_VERSION → $NEW_INSTALLED)"
