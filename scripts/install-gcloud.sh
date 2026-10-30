#!/usr/bin/env bash
# Instalação local da distribuição oficial Linux x86_64, sem sudo nem alteração de shell.
# Arquivo oficial versionado; SHA-256 e VERSION conferidos na revisão final.
# Origem: https://docs.cloud.google.com/sdk/docs/downloads-versioned-archives
set -euo pipefail

if command -v gcloud >/dev/null 2>&1; then
  gcloud version
  exit 0
fi

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo 'Use o instalador da sua plataforma: https://docs.cloud.google.com/sdk/docs/install-sdk' >&2
  exit 1
fi

sdk_version='591.0.0'
sdk_checksum='78c570f5fcfe58a9311bd98c06b75530595e3cae6277aad75a676a39e6ee7b63'
sdk_root="${XDG_DATA_HOME:-$HOME/.local/share}/demarco-google-cloud-cli/$sdk_version"
sdk_bin="$HOME/.local/bin/gcloud"
sdk_tmp="$(mktemp -d)"
trap 'rm -rf -- "$sdk_tmp"' EXIT

if [[ -e "$sdk_bin" || -L "$sdk_bin" ]]; then
  echo "Já existe $sdk_bin; ajuste seu PATH para usá-lo, sem sobrescrevê-lo." >&2
  exit 1
fi

if [[ ! -x "$sdk_root/google-cloud-sdk/bin/gcloud" ]]; then
  curl --fail --location --retry 2 \
    "https://storage.googleapis.com/cloud-sdk-release/google-cloud-cli-${sdk_version}-linux-x86_64.tar.gz" \
    --output "$sdk_tmp/gcloud.tar.gz"
  printf '%s  %s\n' "$sdk_checksum" "$sdk_tmp/gcloud.tar.gz" | sha256sum --check
  mkdir -p "$sdk_root"
  tar --extract --gzip --file "$sdk_tmp/gcloud.tar.gz" --directory "$sdk_root" --no-same-owner
fi
mkdir -p "$HOME/.local/bin"
ln -s "$sdk_root/google-cloud-sdk/bin/gcloud" "$sdk_bin"
CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true "$sdk_bin" version
echo 'Instalado em ~/.local/bin/gcloud. Inclua ~/.local/bin no PATH caso necessário.'
