#!/usr/bin/env bash
#
# Mirror an upstream model at a pinned revision, and archive the evidence of its licence.
#
#   ./scripts/mirror-weights.sh --dry-run Wan-AI/Wan2.2-TI2V-5B
#   ./scripts/mirror-weights.sh Wan-AI/Wan2.2-TI2V-5B
#   ./scripts/mirror-weights.sh --revision 921dbaf... Wan-AI/Wan2.2-TI2V-5B
#
# WHY. An Apache-2.0 grant is irrevocable (§2), so upstream cannot un-license a
# revision already published. What upstream CAN do is delete the repo, gate it, or
# edit the model card. Since none of these repos ship a LICENSE file — the licence
# is declared only in the YAML frontmatter of an ordinary, editable README.md — the
# evidence of the grant is the card as it read at a specific commit. So we archive
# the card, hash it, and mirror the weights beside it.
#
# WHERE. Not Hugging Face. The mirror exists to survive the Hub removing something;
# a copy on the same Hub goes with it. Point BEENGA_MIRROR at object storage on
# unrelated infrastructure (R2, B2, S3).
#
# This script never deletes anything and never writes to the upstream repo.
set -euo pipefail

DRY=0
REVISION=""
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY=1; shift ;;
    --revision) REVISION="$2"; shift 2 ;;
    -h|--help)  sed -n '2,25p' "$0"; exit 0 ;;
    *)          ARGS+=("$1"); shift ;;
  esac
done

if [[ ${#ARGS[@]} -ne 1 ]]; then
  echo "usage: $0 [--dry-run] [--revision SHA] <hf-org/model>" >&2
  exit 1
fi

REPO="${ARGS[0]}"
SLUG="$(echo "$REPO" | tr '/[:upper:]' '-[:lower:]')"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LICDIR="$ROOT/licenses/$SLUG"

: "${BEENGA_MIRROR:=}"   # e.g. r2:beenga-weights   (an rclone remote)

for tool in curl python3; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done

# ── resolve the revision and the declared licence ────────────────────────────

META="$(curl -fsSL "https://huggingface.co/api/models/$REPO")"
SHA="${REVISION:-$(printf '%s' "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin)["sha"])')}"
LICENSE="$(printf '%s' "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("cardData",{}).get("license"))')"

echo "repo      $REPO"
echo "revision  $SHA"
echo "licence   $LICENSE"

case "$LICENSE" in
  apache-2.0|mit|None) ;;
  *) echo ""
     echo "  NOTE: '$LICENSE' is not a permissive licence. Mirroring is fine, but"
     echo "  anything derived from this component inherits '$LICENSE' and must not"
     echo "  be described as Apache-2.0. Record this in PROVENANCE.md." ;;
esac

# ── archive the card, which IS the licence statement ─────────────────────────

CARD="$LICDIR/MODEL_CARD@$SHA.md"
if [[ $DRY -eq 1 ]]; then
  echo ""
  echo "dry run — would archive card to $CARD"
else
  mkdir -p "$LICDIR"
  curl -fsSL "https://huggingface.co/$REPO/raw/$SHA/README.md" -o "$CARD"
  # Some repos do ship a LICENSE despite the general pattern. Take it if present.
  curl -fsSL "https://huggingface.co/$REPO/raw/$SHA/LICENSE" -o "$LICDIR/LICENSE@$SHA" 2>/dev/null || true
  ( cd "$LICDIR" && shasum -a 256 ./*"@$SHA"* > "sha256@$SHA.txt" )
  echo ""
  echo "archived  $CARD"
  cat "$LICDIR/sha256@$SHA.txt"
fi

# ── mirror the weights ───────────────────────────────────────────────────────

if [[ -z "$BEENGA_MIRROR" ]]; then
  echo ""
  echo "BEENGA_MIRROR not set — skipping the weight mirror."
  echo "Set it to an rclone remote on infrastructure that is NOT Hugging Face, e.g."
  echo "  export BEENGA_MIRROR=r2:beenga-weights"
  exit 0
fi

DEST="$BEENGA_MIRROR/$SLUG/$SHA/"
if [[ $DRY -eq 1 ]]; then
  echo "dry run — would download at $SHA and copy to $DEST"
  exit 0
fi

command -v huggingface-cli >/dev/null || { echo "missing: huggingface-cli (pip install -U huggingface_hub)" >&2; exit 1; }
command -v rclone          >/dev/null || { echo "missing: rclone" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo ""
echo "downloading $REPO at $SHA ..."
huggingface-cli download "$REPO" --revision "$SHA" --local-dir "$STAGE"

echo "copying to $DEST ..."
rclone copy "$STAGE" "$DEST" --progress

echo ""
echo "mirrored  $DEST"
echo "Now update the row for \`$REPO\` in PROVENANCE.md to status 'locked'."
