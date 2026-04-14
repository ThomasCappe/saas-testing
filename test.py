#!/usr/bin/env bash
set -euo pipefail

read -rp "URL Artifactory (ex: https://mon-artifactory.example.com/artifactory) : " ART_URL
read -rp "Repo source REMOTE : " SRC_REMOTE
read -rp "Repo cible LOCAL : " DST_LOCAL
read -rp "Collection (ex: community.general) : " COLLECTION
read -rp "Version (ex: 1.0.0) : " VERSION
read -rsp "Token : " TOKEN
echo

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/ansible.cfg" <<EOF
[galaxy]
server_list = source

[galaxy_server.source]
url=$ART_URL/api/ansible/$SRC_REMOTE
token=$TOKEN
EOF

echo "Téléchargement depuis le remote..."
(
  cd "$TMP_DIR"
  ANSIBLE_CONFIG="$TMP_DIR/ansible.cfg" \
    ansible-galaxy collection download "${COLLECTION}:${VERSION}"
)

ARCHIVE="$(find "$TMP_DIR" -type f -name '*.tar.gz' | head -n 1)"

if [[ -z "${ARCHIVE:-}" ]]; then
  echo "ERREUR: archive non téléchargée"
  exit 1
fi

echo "Archive téléchargée : $ARCHIVE"
echo "Publication dans le local..."

ansible-galaxy collection publish "$ARCHIVE" \
  -s "$ART_URL/api/ansible/$DST_LOCAL" \
  --token="$TOKEN"

echo "OK : ${COLLECTION}:${VERSION} copié de $SRC_REMOTE vers $DST_LOCAL"
