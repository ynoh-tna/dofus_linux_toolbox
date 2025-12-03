#!/bin/bash

# Current workspace, start at 0
CURRENT_WS=$(wmctrl -d | awk '$2 == "*" {print $1}')

if [ "$CURRENT_WS" -eq 0 ]; then
    wmctrl -s 1
else
    wmctrl -s 0
fi
