#!/usr/bin/env bash
# Zero em dashes anywhere (non-negotiable 5). Also rejects en dashes.
# Fails nonzero on any hit. Excludes .git.
set -u
hits=$(grep -rIP -n $'\u2014|\u2013' --exclude-dir=.git . 2>/dev/null)
if [ -n "$hits" ]; then
  echo "Em or en dash found:"
  echo "$hits"
  exit 1
fi
echo "no em dashes"
exit 0
