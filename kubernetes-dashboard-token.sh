#!/bin/bash

# Check if the script is run by the correct user
if [[ "$(whoami)" != "muser" ]]; then
  echo "Error: This script must be run as user 'muser'." >&2
  exit 1
fi

kubectl -n kubernetes-dashboard create token dashboard-admin-sa --duration=48h
