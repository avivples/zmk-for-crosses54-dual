#!/usr/bin/env bash
# Regenerate keymap-drawer/crosses.{yaml,svg} from config/crosses.keymap.
#
# Requires: pip install keymap-drawer
# Run from anywhere: ./keymap-drawer/regen.sh

set -euo pipefail

cd "$(dirname "$0")/.."

CFG=keymap_drawer.config.yaml
KEYMAP=config/crosses.keymap
YAML=keymap-drawer/crosses.yaml
SVG=keymap-drawer/crosses.svg

python -m keymap_drawer -c "$CFG" parse -z "$KEYMAP" -o "$YAML"

# keymap-drawer can't auto-detect the gggw shield's physical layout, so
# rewrite the first line to a split-ortho 12x4 + 3-key thumb cluster.
sed -i '1c\layout: {ortho_layout: {split: true, rows: 4, columns: 6, thumbs: 3}}' "$YAML"

python -m keymap_drawer -c "$CFG" draw "$YAML" -o "$SVG"

echo "wrote $YAML and $SVG"
