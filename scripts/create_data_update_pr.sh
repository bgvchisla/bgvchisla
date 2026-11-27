#!/usr/bin/env bash
set -euo pipefail
OUTPUT_FILE="${1:?Expected output file}"
COMMIT_MESSAGE="${2:?Expected commit message}"
REPOSITORY="${GITHUB_REPOSITORY:?Missing repository}"
RUN_ID="${GITHUB_RUN_ID:?Missing run id}"
: "${GH_TOKEN:?Missing GitHub token}"

case "$OUTPUT_FILE" in
  source_status.json|economy.json|official_bnb.json|official_business_climate.json|inflation.json|labour-market.json|news.json|official_fiscal.json|official_nssi.json) ;;
  *) echo "Refusing unapproved data path: $OUTPUT_FILE" >&2; exit 2 ;;
esac

if [[ "$OUTPUT_FILE" == official_bnb.json || "$OUTPUT_FILE" == official_business_climate.json || "$OUTPUT_FILE" == official_nssi.json ]]; then
  git add -f -- "$OUTPUT_FILE"
else
  git add -- "$OUTPUT_FILE"
fi
if git diff --cached --quiet -- "$OUTPUT_FILE"; then
  echo "No changes for $OUTPUT_FILE."
  echo "changed=false" >> "$GITHUB_OUTPUT"
  exit 0
fi

APP_SLUG="${APP_SLUG:-}"
if [[ -n "$APP_SLUG" ]]; then
  BOT_USER_ID="$(gh api "/users/${APP_SLUG}[bot]" --jq .id)"
  git config user.name "${APP_SLUG}[bot]"
  git config user.email "${BOT_USER_ID}+${APP_SLUG}[bot]@users.noreply.github.com"
else
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
fi

SLUG="$(printf '%s' "${GITHUB_WORKFLOW:-data-update}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g')"
BRANCH="automation/data-update-${SLUG}-${RUN_ID}"
git switch -c "$BRANCH"
git commit -m "$COMMIT_MESSAGE"
git push --set-upstream origin "$BRANCH"

OPEN_PR_COUNT="$(gh pr list --repo "$REPOSITORY" --head "$BRANCH" --state open --json number --jq 'length')"
if [[ "$OPEN_PR_COUNT" != "0" ]]; then
  echo "An open PR already exists for $BRANCH; refusing duplicate creation." >&2
  exit 1
fi
gh pr create --repo "$REPOSITORY" --base main --head "$BRANCH" \
  --title "$COMMIT_MESSAGE" \
  --body "Автоматично генериран набор от данни: `$OUTPUT_FILE`.

Промяната е подадена чрез отделен branch и PR. Публикуването в production се извършва единствено след успешно преминаване на задължителните проверки и merge към `main`."
echo "changed=true" >> "$GITHUB_OUTPUT"
