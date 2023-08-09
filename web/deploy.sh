#!/bin/bash
set -euo pipefail
hugo
rsync -avz public/ skookum:/srv/www/bl.skookum.cc
