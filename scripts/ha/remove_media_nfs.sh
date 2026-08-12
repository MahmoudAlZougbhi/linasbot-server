#!/usr/bin/env bash
# Remove legacy meta_social_post_media NFS share (product-disabled Create Post).
# Keeps meta_registry NFS until Managed Postgres cutover.
# Does NOT merge/deploy, purchase Spaces/PG, or enable BOC.
set -euo pipefail

NODE01_PRIV="10.106.0.3"
NODE02_PRIV="10.106.0.4"
DATA_ROOT="/opt/linasbot_data"
MEDIA_DIR="${DATA_ROOT}/meta_social_post_media"
REG_DIR="${DATA_ROOT}/meta_registry"
EXPORTS="/etc/exports"
ROLE="${1:-}"

if [[ "$ROLE" != "node01" && "$ROLE" != "node02" ]]; then
  echo "usage: $0 node01|node02" >&2
  exit 2
fi

echo "[ha-media-remove] role=$ROLE hostname=$(hostname)"

if [[ "$ROLE" == "node02" ]]; then
  if mountpoint -q "${MEDIA_DIR}"; then
    umount "${MEDIA_DIR}" || umount -l "${MEDIA_DIR}"
    echo "[ha-media-remove] umounted ${MEDIA_DIR}"
  fi
  if grep -qF "${NODE01_PRIV}:${MEDIA_DIR}" /etc/fstab; then
    cp -a /etc/fstab "/etc/fstab.bak.media-remove.$(date +%s)"
    grep -vF "${NODE01_PRIV}:${MEDIA_DIR}" /etc/fstab > /tmp/fstab.media-remove
    mv /tmp/fstab.media-remove /etc/fstab
    echo "[ha-media-remove] fstab media line removed"
  fi
  mkdir -p "${MEDIA_DIR}"
  # local empty stub so path exists; product module disabled
  echo "legacy-removed $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${MEDIA_DIR}/.legacy_removed"
  echo "[ha-media-remove] DONE node02"
  exit 0
fi

# node01: drop media export, keep registry export
NFS_MARKER="# linas-ha-share"
TMP_EXP="$(mktemp)"
if [[ -f "${EXPORTS}" ]]; then
  awk -v m="${NFS_MARKER}" '
    $0 ~ m {skip=1; next}
    skip && /^[^#]/ && NF {skip=0}
    skip && /^$/ {next}
    skip {next}
    {print}
  ' "${EXPORTS}" > "${TMP_EXP}" || cp "${EXPORTS}" "${TMP_EXP}"
else
  : > "${TMP_EXP}"
fi
cat >> "${TMP_EXP}" <<EOF
${NFS_MARKER}
${REG_DIR} ${NODE02_PRIV}(rw,sync,no_subtree_check,no_root_squash)
EOF
mv "${TMP_EXP}" "${EXPORTS}"
exportfs -ra
exportfs -v | sed 's/^/[ha-media-remove] export /' || true
echo "legacy-removed $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${MEDIA_DIR}/.legacy_removed"
echo "[ha-media-remove] DONE node01 (registry NFS kept; media export removed)"
