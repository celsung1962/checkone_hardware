# CI setup for the kicad/kicad image (bitbucket-pipelines.yml): sourced, not executed -  . tools/hw_checks/ci_setup.sh
# Environment, KiCad library tables for a fresh user, Python packages of tools/hw_checks.
export PYTHONUTF8=1 HOME=/root KICAD10_SYMBOL_DIR=/usr/share/kicad/symbols KICAD10_FOOTPRINT_DIR=/usr/share/kicad/footprints
# a fresh user has no global sym/fp-lib-table: without them ERC / DRC flag every library link
cfg="$HOME/.config/kicad/10.0"; mkdir -p "$cfg"
for t in sym-lib-table fp-lib-table; do
  if [ -f "/usr/share/kicad/template/$t" ]; then cp "/usr/share/kicad/template/$t" "$cfg/$t"
  else echo "WARNING: no $t template in the image"; fi
done
ls -d /usr/share/kicad/symbols /usr/share/kicad/footprints 2>&1 | sed 's/^/libraries: /'
need=""
python3 -m pip --version >/dev/null 2>&1 || need="$need python3-pip"
command -v curl >/dev/null 2>&1 || need="$need curl"
command -v git >/dev/null 2>&1 || need="$need git"
if [ -n "$need" ]; then apt-get update -qq && apt-get install -y -qq $need >/dev/null; fi
python3 -m pip install -q --break-system-packages -r tools/hw_checks/requirements.txt
git config --global --add safe.directory "${BITBUCKET_CLONE_DIR:-$PWD}"
