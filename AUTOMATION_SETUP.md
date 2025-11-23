# 自動デプロイ設定手順 (GitHub Actions + Cloud Run)

このガイドでは、GitHub Actions を使用して Cloud Run へのデプロイを自動化するための設定手順を説明します。
セキュリティのために、**Workload Identity Federation** を使用して GitHub と Google Cloud を安全に連携させます。

## 前提条件

- Google Cloud プロジェクトが作成済みであること
- `gcloud` コマンドがインストールされ、ログイン済みであること
- GitHub リポジトリの管理者権限があること

## 手順

### 1. 環境変数の設定

ターミナルで以下の変数を設定してください（ご自身の環境に合わせて変更してください）。

```bash
export PROJECT_ID="<YOUR_PROJECT_ID>"
export REGION="asia-northeast1"
export SERVICE_ACCOUNT="github-actions-deployer"
export POOL_NAME="github-actions-pool"
export PROVIDER_NAME="github-actions-provider"
export REPO="<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>" # 例: user/repo
```

### 2. 必要な API の有効化

```bash
gcloud services enable iamcredentials.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### 3. サービスアカウントの作成

GitHub Actions が使用するサービスアカウントを作成します。

```bash
gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
  --display-name="GitHub Actions Deployer"
```

### 4. 権限の付与

サービスアカウントに必要な権限を付与します。

```bash
# Cloud Run へのデプロイ権限
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

# サービスアカウントユーザー（Cloud Run が他のサービスアカウントとして動作するために必要）
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Artifact Registry への書き込み権限
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

### 5. Workload Identity Federation の設定

GitHub Actions からの認証を受け入れるための設定を行います。

```bash
# プールの作成
gcloud iam workload-identity-pools create "${POOL_NAME}" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# プロバイダの作成
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_NAME}" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_NAME}" \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# サービスアカウントとプールの紐付け（特定のリポジトリからのみ許可）
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${REPO}"
```

### 6. GitHub Secrets の設定

GitHub リポジトリの `Settings` > `Secrets and variables` > `Actions` に以下の Secret を追加してください。

| Secret 名 | 値 | 説明 |
|---|---|---|
| `GCP_PROJECT_ID` | `${PROJECT_ID}` の値 | Google Cloud プロジェクト ID |
| `GCP_SERVICE_ACCOUNT` | `${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com` | 作成したサービスアカウントのメールアドレス |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | 以下のコマンドの出力結果 | Workload Identity プロバイダの完全なリソース名 |

**`GCP_WORKLOAD_IDENTITY_PROVIDER` の値を取得するコマンド:**

```bash
gcloud iam workload-identity-pools providers describe "${PROVIDER_NAME}" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_NAME}" \
  --format="value(name)"
```
(出力例: `projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider`)

### 7. 完了

設定が完了したら、`main` ブランチにコードをプッシュすると、自動的にビルドとデプロイが開始されます。
Actions タブで進行状況を確認できます。
