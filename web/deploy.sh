#!/bin/bash
set -euo pipefail
hugo
rsync -avz --delete public/ skookum:/srv/www/bl.skookum.cc
