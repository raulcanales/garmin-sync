#!/usr/bin/env bash
# Build linux/amd64 image and push to the Unraid registry.
#
# Requires Docker Desktop "insecure-registries" for HTTP registries:
#   Settings → Docker Engine → add "insecure-registries": ["10.0.0.60:5001"]
#   Apply & Restart
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REGISTRY="${REGISTRY:-10.0.0.60:5001}"
IMAGE_NAME="${IMAGE_NAME:-garmin-sync}"
TAG="${TAG:-latest}"
IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
PLATFORM="${PLATFORM:-linux/amd64}"

insecure_registry_help() {
  cat >&2 <<EOF

Push failed: Docker used HTTPS but ${REGISTRY} is an HTTP-only registry.

Add it to Docker Desktop → Settings → Docker Engine:

  "insecure-registries": ["${REGISTRY}"]

Click Apply & Restart, then re-run:

  ./scripts/publish.sh

EOF
}

use_host_builder() {
  # Docker Desktop ships builders that use the "docker" driver. Push via
  # "docker push" then respects insecure-registries; buildx --push does not.
  if docker buildx inspect desktop-linux >/dev/null 2>&1; then
    docker buildx use desktop-linux
  else
    docker buildx use default
  fi
}

if ! docker buildx version >/dev/null 2>&1; then
  echo "docker buildx is required." >&2
  exit 1
fi

use_host_builder

echo "Building ${IMAGE} (${PLATFORM})..."
docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE}" \
  --load \
  .

echo "Pushing ${IMAGE}..."
set +e
push_out="$(docker push "${IMAGE}" 2>&1)"
push_status=$?
set -e

if [[ ${push_status} -ne 0 ]]; then
  echo "${push_out}" >&2
  if echo "${push_out}" | grep -q "HTTP response to HTTPS client"; then
    insecure_registry_help
  fi
  exit "${push_status}"
fi

echo "${push_out}"

echo
echo "Published ${IMAGE}"
echo "On Unraid, pull/restart the garmin-sync container to pick up the new image."
