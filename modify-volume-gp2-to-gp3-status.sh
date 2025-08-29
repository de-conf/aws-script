#!/bin/bash

declare -A last_progress

while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="

  volumes=$(aws ec2 describe-volumes-modifications \
    --filters Name=modification-state,Values=optimizing \
    --query 'VolumesModifications[*].[VolumeId,Progress]' \
    --output text)

  if [[ -z "$volumes" ]]; then
    echo "No volumes optimizing."
  else
    while read -r volume_id progress; do
      last=${last_progress[$volume_id]:-0}
      change=$((progress - last))
      printf "%s: %d%% (change: %+d%%)\n" "$volume_id" "$progress" "$change"
      last_progress[$volume_id]=$progress
    done <<< "$volumes"
  fi

  echo ""
  sleep 10
done

