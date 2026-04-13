"""Accuracy benchmark script for investor-intel API.

Calls the deployed (or local) service with curated scenarios, evaluates each
response against spec expectations, and writes a CSV with one row per check.

Usage:
    python scripts/accuracy_benchmark.py
    python scripts/accuracy_benchmark.py --base-url http://localhost:8000
    python scripts/accuracy_benchmark.py --output context/my_run.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Valid enum sets — keep in sync with app/models/
# ---------------------------------------------------------------------------
VALID_TIERS = {"Tier 1", "Tier 2", "Below Threshold"}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
VALID_PRIORITY = {"HIGH", "MEDIUM", "LOW"}
VALID_X_SIGNAL_TYPE = {
    "thesis_statement", "conference_signal", "fund_activity",
    "portfolio_mention", "hiring_signal", "general_activity",
}
VALID_SOURCE = {"discovery", "client_provided"}
VALID_BUCKET = {"High", "Medium", "Low"}
VALID_GRANT_CONFIDENCE = {"high", "medium", "low"}
VALID_WINDOW = {"immediate", "this_week", "monitor"}
VALID_PRIORITY_LOWER = {"high", "medium", "low"}

CSV_FIELDS = [
    "run_id", "timestamp", "scenario_id", "endpoint",
    "entity", "check_id", "field_path", "expected", "actual", "status", "note",
]

DEFAULT_BASE_URL = "https://investor-intel-kdnj.onrender.com"
DEFAULT_OUTPUT_DIR = "context/accuracy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_nested(data: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is None:
            return default
    return data


def expected_tier(score: int) -> str:
    if score >= 75:
        return "Tier 1"
    if score >= 60:
        return "Tier 2"
    return "Below Threshold"


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

class BenchmarkRun:
    def __init__(self, base_url: str, run_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.rows: list[dict] = []
        self.client = httpx.Client(timeout=120.0)

    def _row(
        self,
        scenario_id: str,
        endpoint: str,
        entity: str,
        check_id: str,
        field_path: str,
        expected: Any,
        actual: Any,
        passed: bool | None,  # None → SKIP
        note: str = "",
    ) -> None:
        if passed is None:
            status = "SKIP"
        else:
            status = "PASS" if passed else "FAIL"
        self.rows.append({
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario_id": scenario_id,
            "endpoint": endpoint,
            "entity": entity,
            "check_id": check_id,
            "field_path": field_path,
            "expected": str(expected),
            "actual": str(actual),
            "status": status,
            "note": note,
        })

    def _call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        try:
            if method == "POST":
                resp = self.client.post(url, json=payload)
            else:
                resp = self.client.get(url)
            return resp.status_code, resp.json()
        except Exception as exc:
            return 0, {"error": str(exc)}

    # ------------------------------------------------------------------
    # S1 + S2 — /score-investors
    # ------------------------------------------------------------------

    def run_score_investors(self, scenario_id: str, payload: dict) -> None:
        ep = "/score-investors"
        status_code, body = self._call("POST", ep, payload)

        ok = status_code == 200
        self._row(scenario_id, ep, "request", "http_status", "status_code", 200, status_code, ok)
        if not ok:
            self._row(scenario_id, ep, "request", "success", "success", True, None, None, "skipped — HTTP failed")
            return

        success = body.get("success")
        self._row(scenario_id, ep, "request", "success", "success", True, success, success is True)

        data = body.get("data", {})
        results = data.get("results", [])
        advisor_data = data.get("advisor_data", [])

        # advisor count matches results count
        self._row(
            scenario_id, ep, "request",
            "computed.advisor_count_matches", "len(advisor_data)==len(results)",
            len(results), len(advisor_data), len(results) == len(advisor_data),
        )

        # build advisor lookup by investor_name
        advisor_by_name = {a.get("investor_name"): a for a in advisor_data}

        for result in results:
            investor_name = get_nested(result, "investor", "name") or "unknown"

            # composite_score
            score = result.get("composite_score")
            self._row(scenario_id, ep, investor_name, "range.composite_score",
                      "composite_score", "int 0-100", score,
                      isinstance(score, int) and 0 <= score <= 100)

            # investor_tier
            tier = result.get("investor_tier")
            self._row(scenario_id, ep, investor_name, "enum.investor_tier",
                      "investor_tier", f"∈ {VALID_TIERS}", tier, tier in VALID_TIERS)

            # computed tier vs score
            if isinstance(score, int) and tier in VALID_TIERS:
                exp_tier = expected_tier(score)
                self._row(scenario_id, ep, investor_name, "computed.tier_vs_score",
                          "investor_tier matches composite_score threshold",
                          exp_tier, tier, tier == exp_tier,
                          f"score={score}")

            # investor_source
            source = result.get("investor_source")
            self._row(scenario_id, ep, investor_name, "enum.investor_source",
                      "investor_source", f"∈ {VALID_SOURCE}", source, source in VALID_SOURCE)

            # confidence
            conf = result.get("confidence", {})
            conf_tier = get_nested(conf, "tier") if isinstance(conf, dict) else None
            conf_score = get_nested(conf, "score") if isinstance(conf, dict) else None
            self._row(scenario_id, ep, investor_name, "enum.confidence.tier",
                      "confidence.tier", f"∈ {VALID_CONFIDENCE}", conf_tier,
                      conf_tier in VALID_CONFIDENCE)
            self._row(scenario_id, ep, investor_name, "range.confidence.score",
                      "confidence.score", "float 0.0-1.0", conf_score,
                      isinstance(conf_score, (int, float)) and 0.0 <= conf_score <= 1.0)

            # narrative_summary
            summary = result.get("narrative_summary")
            self._row(scenario_id, ep, investor_name, "nonempty.narrative_summary",
                      "narrative_summary", "non-empty string", summary,
                      bool(summary and isinstance(summary, str)))

            # top_claims count
            claims = result.get("top_claims", [])
            self._row(scenario_id, ep, investor_name, "count.top_claims",
                      "top_claims", "3-5 items", len(claims),
                      3 <= len(claims) <= 5)

            # suggested_contact
            contact = result.get("suggested_contact")
            self._row(scenario_id, ep, investor_name, "nonempty.suggested_contact",
                      "suggested_contact", "non-empty string", contact,
                      bool(contact and isinstance(contact, str)))

            # dimension_strengths buckets
            ds = result.get("dimension_strengths") or {}
            for axis in ("strategic_fit", "stage_relevance", "capital_alignment",
                         "market_activity", "geographic_proximity"):
                val = ds.get(axis)
                self._row(scenario_id, ep, investor_name, f"enum.dimension_strengths.{axis}",
                          f"dimension_strengths.{axis}", f"∈ {VALID_BUCKET}", val,
                          val in VALID_BUCKET)

            # scientific_depth check (passed via note in scenario)
            sci = ds.get("scientific_depth")
            if scenario_id == "score_investors_diagnostics_no_fda":
                self._row(scenario_id, ep, investor_name, "null.dimension_strengths.scientific_depth",
                          "dimension_strengths.scientific_depth", "null (no FDA keyword)", sci,
                          sci is None, "needs_sci_reg()=False for non-FDA thesis")

            # advisor_data outreach_angle + full_axis_breakdown
            advisor = advisor_by_name.get(investor_name)
            if advisor:
                angle = advisor.get("outreach_angle")
                self._row(scenario_id, ep, investor_name, "nonempty.advisor_data.outreach_angle",
                          "advisor_data.outreach_angle", "non-empty string", angle,
                          bool(angle and isinstance(angle, str)))

                fab = advisor.get("full_axis_breakdown") or {}
                for axis in ("thesis_alignment", "stage_fit", "check_size_fit", "recency", "geography"):
                    val = fab.get(axis)
                    self._row(scenario_id, ep, investor_name, f"range.advisor_data.full_axis_breakdown.{axis}",
                              f"full_axis_breakdown.{axis}", "int 0-100", val,
                              isinstance(val, (int, float)) and 0 <= val <= 100)

                sci_fit = fab.get("scientific_regulatory_fit")
                if scenario_id == "score_investors_diagnostics_no_fda":
                    self._row(scenario_id, ep, investor_name,
                              "null.advisor_data.full_axis_breakdown.scientific_regulatory_fit",
                              "full_axis_breakdown.scientific_regulatory_fit", "null (no FDA keyword)", sci_fit,
                              sci_fit is None, "needs_sci_reg()=False")
                else:
                    self._row(scenario_id, ep, investor_name,
                              "range.advisor_data.full_axis_breakdown.scientific_regulatory_fit",
                              "full_axis_breakdown.scientific_regulatory_fit", "int 0-100", sci_fit,
                              isinstance(sci_fit, (int, float)) and 0 <= sci_fit <= 100,
                              "FDA thesis — should be scored")
            else:
                self._row(scenario_id, ep, investor_name, "nonempty.advisor_data.outreach_angle",
                          "advisor_data.outreach_angle", "non-empty string", "MISSING",
                          False, "investor not found in advisor_data")

    # ------------------------------------------------------------------
    # S3 + S4 — /analyze-signal
    # ------------------------------------------------------------------

    def run_analyze_signal(self, scenario_id: str, payload: dict) -> None:
        ep = "/analyze-signal"
        status_code, body = self._call("POST", ep, payload)

        ok = status_code == 200
        self._row(scenario_id, ep, "request", "http_status", "status_code", 200, status_code, ok)
        if not ok:
            return

        success = body.get("success")
        self._row(scenario_id, ep, "request", "success", "success", True, success, success is True)

        analysis = get_nested(body, "data", "analysis") or {}

        # priority
        priority = analysis.get("priority")
        self._row(scenario_id, ep, "signal", "enum.priority",
                  "analysis.priority", f"∈ {VALID_PRIORITY}", priority,
                  priority in VALID_PRIORITY)

        # relevance_score
        rel = analysis.get("relevance_score")
        self._row(scenario_id, ep, "signal", "range.relevance_score",
                  "analysis.relevance_score", "int 0-100", rel,
                  isinstance(rel, (int, float)) and 0 <= rel <= 100)

        # confidence
        conf = analysis.get("confidence", {})
        conf_tier = get_nested(conf, "tier") if isinstance(conf, dict) else None
        self._row(scenario_id, ep, "signal", "enum.confidence.tier",
                  "analysis.confidence.tier", f"∈ {VALID_CONFIDENCE}", conf_tier,
                  conf_tier in VALID_CONFIDENCE)

        # rationale
        rationale = analysis.get("rationale")
        self._row(scenario_id, ep, "signal", "nonempty.analysis.rationale",
                  "analysis.rationale", "non-empty string", rationale,
                  bool(rationale and isinstance(rationale, str)))

        # expires_relevance (computed field — should be a date string)
        expires = analysis.get("expires_relevance")
        self._row(scenario_id, ep, "signal", "nonempty.analysis.expires_relevance",
                  "analysis.expires_relevance", "non-empty string", expires,
                  bool(expires and isinstance(expires, str)))

        # briefing fields
        briefing = analysis.get("briefing") or {}
        for field in ("headline", "why_it_matters", "outreach_angle", "suggested_contact", "time_sensitivity"):
            val = briefing.get(field) if isinstance(briefing, dict) else None
            self._row(scenario_id, ep, "signal", f"nonempty.briefing.{field}",
                      f"briefing.{field}", "non-empty string", val,
                      bool(val and isinstance(val, str)))

        # x_signal_type
        x_type = analysis.get("x_signal_type")
        signal_type = payload.get("signal_type")
        if signal_type == "X_GROK":
            self._row(scenario_id, ep, "signal", "enum.x_signal_type",
                      "analysis.x_signal_type", f"∈ {VALID_X_SIGNAL_TYPE}", x_type,
                      x_type in VALID_X_SIGNAL_TYPE)
        else:
            self._row(scenario_id, ep, "signal", "null.x_signal_type",
                      "analysis.x_signal_type", "null (non-X signal)", x_type,
                      x_type is None)

    # ------------------------------------------------------------------
    # S5 — /generate-digest
    # ------------------------------------------------------------------

    def run_generate_digest(self, scenario_id: str, payload: dict) -> None:
        ep = "/generate-digest"
        status_code, body = self._call("POST", ep, payload)

        ok = status_code == 200
        self._row(scenario_id, ep, "request", "http_status", "status_code", 200, status_code, ok)
        if not ok:
            return

        success = body.get("success")
        self._row(scenario_id, ep, "request", "success", "success", True, success, success is True)

        data = body.get("data", {})
        client_digest = data.get("client_digest") or {}
        internal_digest = data.get("internal_digest") or {}

        # client_digest fields
        subject = client_digest.get("subject")
        self._row(scenario_id, ep, "client_digest", "nonempty.client_digest.subject",
                  "client_digest.subject", "non-empty string", subject,
                  bool(subject and isinstance(subject, str)))

        sections = client_digest.get("sections") or []
        self._row(scenario_id, ep, "client_digest", "count.client_digest.sections",
                  "client_digest.sections", "≥ 1", len(sections), len(sections) >= 1)

        x_activity = client_digest.get("x_activity_section") or {}
        section_title = x_activity.get("section_title")
        self._row(scenario_id, ep, "client_digest", "nonempty.client_digest.x_activity_section.section_title",
                  "x_activity_section.section_title", "non-empty string", section_title,
                  bool(section_title and isinstance(section_title, str)))

        x_signals_input = payload.get("x_signals") or []
        x_signals_out = x_activity.get("signals") or []
        if x_signals_input:
            self._row(scenario_id, ep, "client_digest", "count.client_digest.x_activity_section.signals",
                      "x_activity_section.signals", "≥ 1 (x_signals provided)", len(x_signals_out),
                      len(x_signals_out) >= 1)

        # internal_digest fields
        key_insights = internal_digest.get("key_insights") or []
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.key_insights",
                  "internal_digest.key_insights", "1-5 items", len(key_insights),
                  1 <= len(key_insights) <= 5)

        outreach_angles = internal_digest.get("outreach_angles") or []
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.outreach_angles",
                  "internal_digest.outreach_angles", "≥ 1", len(outreach_angles),
                  len(outreach_angles) >= 1)

        call_plan = internal_digest.get("call_plan") or {}
        opening = call_plan.get("opening_framing") if isinstance(call_plan, dict) else None
        self._row(scenario_id, ep, "internal_digest", "nonempty.internal_digest.call_plan.opening_framing",
                  "call_plan.opening_framing", "non-empty string", opening,
                  bool(opening and isinstance(opening, str)))

        threads = call_plan.get("discussion_threads") or [] if isinstance(call_plan, dict) else []
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.call_plan.discussion_threads",
                  "call_plan.discussion_threads", "1-5 items", len(threads),
                  1 <= len(threads) <= 5)

        # client_digest preheader
        preheader = client_digest.get("preheader")
        self._row(scenario_id, ep, "client_digest", "nonempty.client_digest.preheader",
                  "client_digest.preheader", "non-empty string", preheader,
                  bool(preheader and isinstance(preheader, str)))

        # call_plan desired_outcome
        desired = call_plan.get("desired_outcome") if isinstance(call_plan, dict) else None
        self._row(scenario_id, ep, "internal_digest", "nonempty.internal_digest.call_plan.desired_outcome",
                  "call_plan.desired_outcome", "non-empty string", desired,
                  bool(desired and isinstance(desired, str)))

        # x_activity_section per-signal enum checks (only when signals are present)
        for i, sig in enumerate(x_signals_out):
            sig_entity = f"x_signal_{i}"
            sig_data = sig if isinstance(sig, dict) else {}

            x_t = sig_data.get("x_signal_type")
            self._row(scenario_id, ep, sig_entity, "enum.x_signal_type",
                      "x_activity_section.signals[].x_signal_type", f"∈ {VALID_X_SIGNAL_TYPE}", x_t,
                      x_t in VALID_X_SIGNAL_TYPE)

            window = sig_data.get("window")
            self._row(scenario_id, ep, sig_entity, "enum.window",
                      "x_activity_section.signals[].window", f"∈ {VALID_WINDOW}", window,
                      window in VALID_WINDOW)

            priority = sig_data.get("priority")
            self._row(scenario_id, ep, sig_entity, "enum.priority",
                      "x_activity_section.signals[].priority", f"∈ {VALID_PRIORITY_LOWER}", priority,
                      priority in VALID_PRIORITY_LOWER)

            sig_summary = sig_data.get("signal_summary")
            self._row(scenario_id, ep, sig_entity, "nonempty.signal_summary",
                      "x_activity_section.signals[].signal_summary", "non-empty string", sig_summary,
                      bool(sig_summary and isinstance(sig_summary, str)))

            action = sig_data.get("recommended_action")
            self._row(scenario_id, ep, sig_entity, "nonempty.recommended_action",
                      "x_activity_section.signals[].recommended_action", "non-empty string", action,
                      bool(action and isinstance(action, str)))

        # internal_digest: likely_objections
        objections = internal_digest.get("likely_objections") or []
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.likely_objections",
                  "internal_digest.likely_objections", "≥ 1", len(objections), len(objections) >= 1)
        if objections:
            first_obj = objections[0] if isinstance(objections[0], dict) else {}
            self._row(scenario_id, ep, "internal_digest", "nonempty.internal_digest.likely_objections[0].objection",
                      "likely_objections[0].objection", "non-empty string", first_obj.get("objection"),
                      bool(first_obj.get("objection") and isinstance(first_obj.get("objection"), str)))

        # internal_digest: risks_sensitivities + questions_to_ask (presence check)
        risks = internal_digest.get("risks_sensitivities")
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.risks_sensitivities",
                  "internal_digest.risks_sensitivities", "list", len(risks) if isinstance(risks, list) else -1,
                  isinstance(risks, list))

        questions = internal_digest.get("questions_to_ask")
        self._row(scenario_id, ep, "internal_digest", "count.internal_digest.questions_to_ask",
                  "internal_digest.questions_to_ask", "list", len(questions) if isinstance(questions, list) else -1,
                  isinstance(questions, list))

        # internal_digest: first outreach_angle fields
        if outreach_angles:
            first_ang = outreach_angles[0] if isinstance(outreach_angles[0], dict) else {}
            self._row(scenario_id, ep, "internal_digest", "nonempty.internal_digest.outreach_angles[0].angle",
                      "outreach_angles[0].angle", "non-empty string", first_ang.get("angle"),
                      bool(first_ang.get("angle") and isinstance(first_ang.get("angle"), str)))
            self._row(scenario_id, ep, "internal_digest", "nonempty.internal_digest.outreach_angles[0].avoid",
                      "outreach_angles[0].avoid", "non-empty string", first_ang.get("avoid"),
                      bool(first_ang.get("avoid") and isinstance(first_ang.get("avoid"), str)))

    # ------------------------------------------------------------------
    # S6 — /score-grants
    # ------------------------------------------------------------------

    def run_score_grants(self, scenario_id: str, payload: dict) -> None:
        ep = "/score-grants"
        status_code, body = self._call("POST", ep, payload)

        ok = status_code == 200
        self._row(scenario_id, ep, "request", "http_status", "status_code", 200, status_code, ok)
        if not ok:
            return

        success = body.get("success")
        self._row(scenario_id, ep, "request", "success", "success", True, success, success is True)

        data = body.get("data", {})
        scored_grants = data.get("scored_grants") or []

        # response-level checks
        self._row(scenario_id, ep, "response", "count.scored_grants",
                  "scored_grants", "≥ 1", len(scored_grants), len(scored_grants) >= 1)

        response_summary = data.get("summary")
        self._row(scenario_id, ep, "response", "nonempty.scored_grants_summary",
                  "data.summary", "non-empty string", response_summary,
                  bool(response_summary and isinstance(response_summary, str)))

        for i, grant in enumerate(scored_grants):
            entity = f"grant_{i}"
            title = grant.get("title") or entity

            score = grant.get("overall_score")
            self._row(scenario_id, ep, title, "range.overall_score",
                      "overall_score", "int 0-100", score,
                      isinstance(score, (int, float)) and 0 <= score <= 100)

            confidence = grant.get("confidence")
            self._row(scenario_id, ep, title, "enum.confidence",
                      "confidence", f"∈ {VALID_GRANT_CONFIDENCE}", confidence,
                      confidence in VALID_GRANT_CONFIDENCE)

            rationale = grant.get("rationale")
            self._row(scenario_id, ep, title, "nonempty.rationale",
                      "rationale", "non-empty string", rationale,
                      bool(rationale and isinstance(rationale, str)))

            breakdown = grant.get("breakdown") or {}
            for axis in ("therapeutic_match", "stage_eligibility", "award_size_relevance",
                         "deadline_feasibility", "historical_funding"):
                val = breakdown.get(axis)
                self._row(scenario_id, ep, title, f"range.breakdown.{axis}",
                          f"breakdown.{axis}", "int 0-100", val,
                          isinstance(val, (int, float)) and 0 <= val <= 100)

    # ------------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------------

    def write_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

    def print_summary(self) -> None:
        total = len(self.rows)
        passed = sum(1 for r in self.rows if r["status"] == "PASS")
        failed = sum(1 for r in self.rows if r["status"] == "FAIL")
        skipped = sum(1 for r in self.rows if r["status"] == "SKIP")
        print(f"\nRun complete — {total} checks: {passed} PASS · {failed} FAIL · {skipped} SKIP")
        if failed:
            print("\nFailed checks:")
            for r in self.rows:
                if r["status"] == "FAIL":
                    print(f"  [{r['scenario_id']}] {r['entity']} / {r['check_id']}"
                          f" — expected {r['expected']!r}, got {r['actual']!r}"
                          + (f" ({r['note']})" if r["note"] else ""))


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def build_scenarios() -> list[tuple[str, str, dict]]:
    """Return list of (scenario_id, endpoint_type, payload)."""
    return [
        # S1 — biotech CAR-T with 2 investors
        ("score_investors_biotech", "score_investors", {
            "client": {
                "name": "NovaBio Therapeutics",
                "thesis": "Developing novel CAR-T cell therapies for solid tumors, seeking FDA Breakthrough Therapy designation",
                "geography": "US",
                "funding_target": "$15M Series A",
            },
            "investors": [
                {"name": "OrbiMed Advisors", "notes": "Healthcare-focused PE/VC, active in oncology"},
                {"name": "Flagship Pioneering", "notes": "Deep biotech platform investor"},
            ],
        }),

        # S2 — diagnostics with no FDA keyword → scientific_depth must be null
        ("score_investors_diagnostics_no_fda", "score_investors", {
            "client": {
                "name": "AxisDx",
                "thesis": "AI diagnostics platform for rare diseases using multi-modal biomarkers",
                "geography": "US",
                "funding_target": "$8M Seed",
            },
            "investors": [
                {"name": "a16z Bio", "notes": "Deep tech healthcare investor"},
            ],
        }),

        # S3 — SEC EDGAR signal (x_signal_type must be null)
        ("analyze_signal_sec", "analyze_signal", {
            "signal_type": "SEC_EDGAR",
            "title": "Form D: OrbiMed Healthcare Fund IX — $750M close",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=orbimed&type=D",
            "published_at": "2026-04-01",
            "raw_text": "OrbiMed Advisors has filed a Form D indicating a $750M close for Healthcare Fund IX, focused on late-stage oncology and rare disease investments.",
            "investor": {
                "name": "OrbiMed Advisors",
                "firm": "OrbiMed",
                "thesis_keywords": ["oncology", "rare disease", "late-stage"],
                "portfolio_companies": ["Blueprint Medicines", "G1 Therapeutics"],
                "key_partners": ["Sven Borho", "Carl Gordon"],
            },
            "client": {
                "name": "NovaBio Therapeutics",
                "thesis": "CAR-T therapies for solid tumors seeking Series A",
                "geography": "US",
                "stage": "Series A",
            },
        }),

        # S4 — X_GROK signal (x_signal_type must be non-null valid enum)
        ("analyze_signal_xgrok", "analyze_signal", {
            "signal_type": "X_GROK",
            "title": "Flagship Pioneering partner tweets about oncology platform thesis",
            "url": "https://x.com/flagshippioneering/status/example123",
            "published_at": "2026-04-03",
            "raw_text": "Our conviction around oncology platform companies has never been stronger. The next wave of CAR-T innovation is happening now. Very active on new Series A opportunities.",
            "x_engagement_data": {
                "replies": 42,
                "reposts": 187,
                "likes": 830,
                "is_original_post": True,
                "author": "David Berry",
                "author_type": "partner",
            },
            "investor": {
                "name": "Flagship Pioneering",
                "firm": "Flagship Pioneering",
                "thesis_keywords": ["platform biotech", "oncology", "CAR-T", "Series A"],
                "portfolio_companies": ["Moderna", "Sana Biotechnology", "Generate Biomedicines"],
                "key_partners": ["David Berry", "Noubar Afeyan"],
            },
            "client": {
                "name": "NovaBio Therapeutics",
                "thesis": "CAR-T therapies for solid tumors seeking Series A",
                "geography": "US",
                "stage": "Series A",
            },
        }),

        # S5 — full digest with x_signals
        ("generate_digest_full", "generate_digest", {
            "client": {
                "name": "NovaBio Therapeutics",
                "geography": "US",
                "therapeutic_area": "Oncology",
                "stage": "Series A",
                "target_raise": "$15M",
            },
            "week_start": "2026-04-07",
            "week_end": "2026-04-11",
            "signals": [
                {
                    "title": "OrbiMed closes $750M Healthcare Fund IX",
                    "url": "https://example.com/orbimed-fund-ix",
                    "summary": "OrbiMed's new fund signals strong conviction in late-stage oncology.",
                },
                {
                    "title": "FDA grants Breakthrough Therapy to solid tumor CAR-T approach",
                    "url": "https://example.com/fda-breakthrough",
                    "summary": "Regulatory tailwind for CAR-T in solid tumors.",
                },
            ],
            "investors": [
                {"name": "OrbiMed Advisors", "pipeline_status": "meeting_scheduled"},
                {"name": "Flagship Pioneering", "pipeline_status": "uncontacted"},
            ],
            "x_signals": [
                {
                    "investor_name": "OrbiMed Advisors",
                    "firm": "OrbiMed",
                    "signal_summary": "Partner tweeted conviction in oncology CAR-T platforms",
                    "x_signal_type": "fund_activity",
                },
                {
                    "investor_name": "Flagship Pioneering",
                    "firm": "Flagship Pioneering",
                    "signal_summary": "Flagship shared hiring post for oncology portfolio company",
                    "x_signal_type": "hiring_signal",
                },
            ],
        }),

        # S6 — grants
        ("score_grants_sbir", "score_grants", {
            "client_profile": {
                "company_name": "NovaBio Therapeutics",
                "therapeutic_area": "Oncology",
                "stage": "Phase 2",
                "fda_pathway": "Breakthrough Therapy",
                "keywords": ["cancer", "immunotherapy", "CAR-T", "solid tumors"],
            },
            "grants": [
                {
                    "source": "NIH",
                    "title": "SBIR Phase II: Novel Cancer Immunotherapy Approaches",
                    "agency": "National Cancer Institute",
                    "program": "SBIR",
                    "award_amount": "$1,500,000",
                    "deadline": "2027-06-30",
                    "description": "Supports innovative small businesses developing novel cancer immunotherapy. Preference for CAR-T, checkpoint inhibitor, and combination approaches in solid tumors.",
                    "eligibility": "Small businesses with fewer than 500 employees. Must have completed Phase I SBIR.",
                    "url": "https://grants.nih.gov/grants/guide/pa-files/PA-21-259.html",
                },
            ],
        }),
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="investor-intel accuracy benchmark")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Service base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output", default=None,
                        help="Output CSV path (default: context/accuracy/run_TIMESTAMP.csv)")
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(DEFAULT_OUTPUT_DIR, f"{run_id}.csv")

    print(f"investor-intel accuracy benchmark")
    print(f"  Base URL : {args.base_url}")
    print(f"  Run ID   : {run_id}")
    print(f"  Output   : {output_path}")
    print()

    runner = BenchmarkRun(base_url=args.base_url, run_id=run_id)
    scenarios = build_scenarios()

    dispatch = {
        "score_investors": runner.run_score_investors,
        "analyze_signal": runner.run_analyze_signal,
        "generate_digest": runner.run_generate_digest,
        "score_grants": runner.run_score_grants,
    }

    for scenario_id, endpoint_type, payload in scenarios:
        print(f"  Running {scenario_id}...", end=" ", flush=True)
        fn = dispatch[endpoint_type]
        try:
            fn(scenario_id, payload)
            checks = [r for r in runner.rows if r["scenario_id"] == scenario_id]
            passed = sum(1 for r in checks if r["status"] == "PASS")
            failed = sum(1 for r in checks if r["status"] == "FAIL")
            print(f"{passed} PASS, {failed} FAIL")
        except Exception as exc:
            print(f"ERROR — {exc}")

    runner.write_csv(output_path)
    runner.print_summary()
    print(f"\nCSV written to: {output_path}")


if __name__ == "__main__":
    main()
