#!/usr/bin/env bash
# Manual endpoint testing script for investor-intel API
# Usage: ./scripts/test_endpoints.sh [BASE_URL]
# Default: http://localhost:8000

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

run_test() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="${5:-200}"

    printf "%-50s " "$name..."
    status=$(curl -s -o /tmp/test_response.json -w "%{http_code}" \
        -X "$method" \
        -H "Content-Type: application/json" \
        -d "$data" \
        "${BASE_URL}${endpoint}")

    if [ "$status" = "$expected_status" ]; then
        echo "PASS ($status)"
        PASS=$((PASS + 1))
    else
        echo "FAIL (got $status, expected $expected_status)"
        cat /tmp/test_response.json | python3 -m json.tool 2>/dev/null || cat /tmp/test_response.json
        echo
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================="
echo "  investor-intel API — endpoint tests"
echo "  Target: $BASE_URL"
echo "========================================="
echo

# Health check
printf "%-50s " "Health check..."
status=$(curl -s -o /tmp/test_response.json -w "%{http_code}" "${BASE_URL}/health")
if [ "$status" = "200" ]; then
    echo "PASS ($status)"
    PASS=$((PASS + 1))
else
    echo "FAIL ($status)"
    FAIL=$((FAIL + 1))
fi

# Score investors — basic
run_test "Score investors (basic)" POST "/score-investors" '{
  "client": {
    "name": "NovaBio Therapeutics",
    "thesis": "Developing novel CAR-T cell therapies for solid tumors",
    "geography": "US",
    "funding_target": "$15M Series A"
  },
  "investors": [
    {"name": "OrbiMed Advisors", "notes": "Healthcare-focused PE/VC"},
    {"name": "ARCH Venture Partners"}
  ]
}'

# Score investors — with funding target
run_test "Score investors (with funding target)" POST "/score-investors" '{
  "client": {
    "name": "MedAxis",
    "thesis": "AI-powered diagnostic platform for rare diseases",
    "funding_target": "$5M Seed"
  },
  "investors": [
    {"name": "a16z Bio"}
  ]
}'

# Analyze signal — SEC filing
run_test "Analyze signal (SEC)" POST "/analyze-signal" '{
  "signal_type": "SEC_EDGAR",
  "title": "Form D filed for NovaBio Series A",
  "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=novabio"
}'

# Analyze signal — with investor + client context
run_test "Analyze signal (with context)" POST "/analyze-signal" '{
  "signal_type": "GOOGLE_NEWS",
  "title": "Flagship Pioneering launches new biotech platform",
  "url": "https://news.example.com/flagship-launch",
  "raw_text": "Flagship Pioneering announced a new platform company focused on immunology...",
  "investor": {
    "name": "Flagship Pioneering",
    "thesis_keywords": ["biotech", "platform", "immunology"],
    "portfolio_companies": ["Moderna", "Sana Biotechnology"]
  },
  "client": {
    "name": "NovaBio",
    "thesis": "Novel immunotherapy approaches",
    "geography": "US"
  }
}'

# Generate digest
run_test "Generate digest" POST "/generate-digest" '{
  "client": {"name": "NovaBio", "geography": "US"},
  "week_start": "2026-03-15",
  "week_end": "2026-03-21",
  "signals": [
    {"title": "FDA grants breakthrough designation", "url": "https://example.com/fda-breakthrough"},
    {"title": "New oncology fund launched", "url": "https://example.com/onc-fund"}
  ]
}'

# Score grants
run_test "Score grants" POST "/score-grants" '{
  "client_profile": {
    "company_name": "NovaBio",
    "therapeutic_area": "Oncology",
    "stage": "Phase 2",
    "fda_pathway": "Breakthrough Therapy",
    "keywords": ["cancer", "immunotherapy", "CAR-T"]
  },
  "grants": [
    {
      "source": "NIH",
      "title": "SBIR Phase II: Novel Cancer Immunotherapy",
      "agency": "National Cancer Institute",
      "program": "SBIR",
      "award_amount": "$1,500,000",
      "deadline": "2027-06-30",
      "description": "Funding for innovative cancer immunotherapy approaches.",
      "eligibility": "Small businesses with <500 employees",
      "url": "https://grants.nih.gov/example"
    }
  ]
}'

# Validation error (empty investors)
run_test "Validation error (empty investors)" POST "/score-investors" '{
  "client": {"name": "Acme", "thesis": "Bio"},
  "investors": []
}' 422

echo
echo "========================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
