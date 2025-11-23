#!/bin/bash
set -e

echo "🚀 Cloud Run 自動デプロイ設定スクリプト"
echo "----------------------------------------"

# 1. プロジェクトIDの確認
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
read -p "Google Cloud プロジェクトID [${CURRENT_PROJECT}]: " INPUT_PROJECT
PROJECT_ID=${INPUT_PROJECT:-$CURRENT_PROJECT}

if [ -z "$PROJECT_ID" ]; then
    echo "❌ プロジェクトIDが指定されていません。"
    exit 1
fi

echo "✅ プロジェクトID: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

# 2. GitHub リポジトリ情報の入力
read -p "GitHub ユーザー名 (例: yuhei): " GITHUB_USER
read -p "GitHub リポジトリ名 (例: esa-summarizer): " GITHUB_REPO

if [ -z "$GITHUB_USER" ] || [ -z "$GITHUB_REPO" ]; then
    echo "❌ GitHub情報が不足しています。"
    exit 1
fi

REPO="${GITHUB_USER}/${GITHUB_REPO}"
echo "✅ 対象リポジトリ: ${REPO}"

# 変数定義
REGION="asia-northeast1"
SERVICE_ACCOUNT="github-actions-deployer"
POOL_NAME="github-actions-pool"
PROVIDER_NAME="github-actions-provider"

echo ""
echo "以下の設定でリソースを作成します:"
echo "- サービスアカウント: ${SERVICE_ACCOUNT}"
echo "- Workload Identity プール: ${POOL_NAME}"
echo "- プロバイダ: ${PROVIDER_NAME}"
echo ""
read -p "続行しますか？ (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "中止しました。"
    exit 0
fi

# 3. API有効化
echo "⏳ APIを有効化しています..."
gcloud services enable iamcredentials.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# 4. サービスアカウント作成
echo "⏳ サービスアカウントを作成しています..."
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
      --display-name="GitHub Actions Deployer"
else
    echo "  (既存のサービスアカウントを使用します)"
fi

# 5. 権限付与
echo "⏳ 権限を付与しています..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" >/dev/null

# 6. Workload Identity Federation 設定
echo "⏳ Workload Identity Federation を設定しています..."

# プール作成
if ! gcloud iam workload-identity-pools describe "${POOL_NAME}" --location="global" >/dev/null 2>&1; then
    gcloud iam workload-identity-pools create "${POOL_NAME}" \
      --project="${PROJECT_ID}" \
      --location="global" \
      --display-name="GitHub Actions Pool"
else
    echo "  (既存のプールを使用します)"
fi

# プロバイダ作成
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_NAME}" --location="global" --workload-identity-pool="${POOL_NAME}" >/dev/null 2>&1; then
    gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_NAME}" \
      --project="${PROJECT_ID}" \
      --location="global" \
      --workload-identity-pool="${POOL_NAME}" \
      --display-name="GitHub Actions Provider" \
      --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
      --issuer-uri="https://token.actions.githubusercontent.com"
else
    echo "  (既存のプロバイダを使用します)"
fi

# 紐付け
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${REPO}" >/dev/null

# 7. 結果表示
PROVIDER_PATH=$(gcloud iam workload-identity-pools providers describe "${PROVIDER_NAME}" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_NAME}" \
  --format="value(name)")

echo ""
echo "✅ 設定が完了しました！"
echo "----------------------------------------"
echo "GitHub の Secrets に以下を登録してください:"
echo ""
echo "GCP_PROJECT_ID: ${PROJECT_ID}"
echo "GCP_SERVICE_ACCOUNT: ${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "GCP_WORKLOAD_IDENTITY_PROVIDER: ${PROVIDER_PATH}"
echo "----------------------------------------"
