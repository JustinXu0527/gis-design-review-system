#!/bin/sh
set -eu

export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &

exec spawn-fcgi -n -p 5555 -d /data -- /usr/lib/cgi-bin/qgis_mapserv.fcgi
