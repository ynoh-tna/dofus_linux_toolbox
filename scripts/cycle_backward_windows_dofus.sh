#!/bin/bash
STATE_FILE="/tmp/dofus_window_index"
CLASS_INI=('Cra' 'Enu' 'Feca')
AVAILABLE=($(wmctrl -l | grep "Dofus-" | awk '{print $4}' | cut -d'-' -f2))
if [[ ${#AVAILABLE[@]} -eq 0 ]]; then exit 1; fi
if [ -f "$STATE_FILE" ]; then INDEX=$(cat "$STATE_FILE"); else INDEX=0; fi
TOTAL=${#CLASS_INI[@]}
for ((i=1; i<=TOTAL; i++)); do
    NEXT=$(( (INDEX - i + TOTAL) % TOTAL ))
    CLASS_NAME=${CLASS_INI[$NEXT]}
    if printf '%s\n' "${AVAILABLE[@]}" | grep -q "^$CLASS_NAME$"; then
        wmctrl -a "Dofus-$CLASS_NAME"
        echo "$NEXT" > "$STATE_FILE"
        exit 0
    fi
done
