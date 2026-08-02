#!/usr/bin/env bash
set -euo pipefail

# Scan only tracked files so local dependencies and generated artifacts cannot
# affect the result. Keep output non-sensitive: a match fails the gate without
# rendering the matched line or credential.
openai_pattern='sk-proj-[A-Za-z0-9_-]{20,}'
meta_pattern='EAA[A-Za-z0-9]{30,}'
default_password_pattern='admin''123'

if git ls-files --error-unmatch config/montymobile_templates.json >/dev/null 2>&1; then
  set +e
  jq -e \
    '.api_config.api_key | type == "string" and length >= 16' \
    config/montymobile_templates.json \
    >/dev/null
  monty_status=$?
  set -e

  case "$monty_status" in
    0)
      echo "Tracked Monty API key must be empty"
      exit 1
      ;;
    1) ;;
    *)
      echo "Secret scan failed to execute" >&2
      exit 2
      ;;
  esac
fi

set +e
git grep -qE \
  -e "$openai_pattern" \
  -e "$meta_pattern" \
  -e "$default_password_pattern" \
  -- \
  . \
  ':(exclude,glob)*.md' \
  ':(exclude,glob)**/*.md' \
  ':(exclude,glob).env*' \
  ':(exclude,glob)**/.env*' \
  ':(exclude,glob)node_modules/**' \
  ':(exclude,glob)**/node_modules/**' \
  ':(exclude,glob).venv*/**' \
  ':(exclude,glob)**/.venv*/**'
scan_status=$?
set -e

case "$scan_status" in
  0)
    echo "Potential secret or default password found in tracked files"
    exit 1
    ;;
  1)
    echo "Secret scan passed"
    ;;
  *)
    echo "Secret scan failed to execute" >&2
    exit 2
    ;;
esac
