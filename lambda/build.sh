#!/usr/bin/env bash
# Build the webhook Lambda as a container image and push to ECR.
#
# Usage:
#   bash lambda/build.sh              # uses defaults (ap-south-1, wactl-dev-webhook)
#   AWS_REGION=ap-south-1 PROJECT=mybot bash lambda/build.sh
#
# Reads ECR registry/login from the standard AWS CLI config.
# Tag defaults to "latest"; override with TAG=<your-tag>.

set -euo pipefail

cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT_PREFIX:-wactl}"
ENV="${ENV:-dev}"
TAG="${TAG:-latest}"
REPO="${PROJECT}-${ENV}-webhook"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${ECR_REGISTRY}/${REPO}:${TAG}"

echo "[lambda_build] ECR repo: ${ECR_REGISTRY}/${REPO}"
echo "[lambda_build] Building ${IMAGE}"

# Ensure the ECR repo exists. Idempotent — the ``ResourceAlreadyExistsException``
# from ``create-repository`` is fine.
aws ecr describe-repositories --repository-names "${REPO}" --region "${REGION}" \
  >/dev/null 2>&1 || \
  aws ecr create-repository \
    --repository-name "${REPO}" \
    --image-scanning-configuration scanOnPush=true \
    --region "${REGION}" \
    --image-tag-mutability MUTABLE >/dev/null

docker build -t "${IMAGE}" -f lambda/Dockerfile .

echo "[lambda_build] Logging in to ECR ${ECR_REGISTRY}"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "[lambda_build] Pushing ${IMAGE}"
docker push "${IMAGE}"

echo
echo "[lambda_build] Done. Image URI:"
echo "  ${IMAGE}"
echo
echo "[lambda_build] Next step:"
echo "  terraform apply \\"
echo "    -var region=${REGION} \\"
echo "    -var lambda_image_tag=${TAG} \\"
echo "    -var telegram_bot_token=... \\"
echo "    -var telegram_webhook_secret_token=..."
