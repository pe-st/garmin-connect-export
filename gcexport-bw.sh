#!/bin/sh
#
# garmin-connect-export integration with BitWarden
#
# This script gets the credentials from BitWarden CLI tool
# and then passes them to `gcexport.py` via --username and --password.
#
# All other arguments can be passed directly to this script
# and will be forwarded to gcexport.py.
#
#
# Usage: gcexport-bw.sh [optional args for gcexport.py]

SESSION=`bw unlock | grep --max-count=1 BW_SESSION= | cut -d \" -f 2`

if [ -z $SESSION ]; then
	exit 1
fi

USER=`bw get username garmin.com --session $SESSION`
PASS=`bw get password garmin.com --session $SESSION`

bw lock

python3 gcexport.py --username $USER --password $PASS "$@"
