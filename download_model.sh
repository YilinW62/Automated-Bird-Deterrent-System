#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models
BASE='https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master'
curl -fL --retry 3 "$BASE/MobileNetSSD_deploy.prototxt" -o models/MobileNetSSD_deploy.prototxt
curl -fL --retry 3 "$BASE/MobileNetSSD_deploy.caffemodel" -o models/MobileNetSSD_deploy.caffemodel
# Guard against HTML error responses / LFS pointers.
test "$(wc -c < models/MobileNetSSD_deploy.prototxt)" -gt 10000
test "$(wc -c < models/MobileNetSSD_deploy.caffemodel)" -gt 10000000
echo 'Model files downloaded and passed basic size checks.'