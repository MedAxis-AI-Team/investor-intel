"""Scoring configuration builder for /score-investors.

Translates client_profile + modifiers into a ScoringInstructions config object
that drives prompt construction in AnthropicLlmClient. No if/else chains —
all branching is handled via lookup dicts so the prompt builder stays generic.

Phase 1.5 compatibility: when scoring_instructions JSON is supplied directly
in the request, parse it into ScoringInstructions and bypass build_scoring_instructions().
The prompt builder in anthropic_client.py does not need to change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CLASSIFIER_VERSION = "1.0.0-phase1"


@dataclass(frozen=True)
class ScoringInstructions:
    """Config object consumed by the LLM prompt builder.

    All fields are derived from client_profile + modifiers (Phase 1) or
    supplied directly as JSON (Phase 1.5). The prompt builder reads only
    from this object — never from if/else profile checks.
    """

    profile_type: str
    thesis_keywords: list[str]
    investor_universe_hints: str
    stage_fit_guidance: str
    sci_reg_guidance: str
    # True = always score scientific_regulatory_fit; False = defer to needs_sci_reg()
    score_scientific_regulatory: bool
    modifier_keywords: list[str] = field(default_factory=list)
    modifier_guidance: str = ""
    classifier_version: str = _CLASSIFIER_VERSION


# ---------------------------------------------------------------------------
# Profile configs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ProfileConfig:
    thesis_keywords: list[str]
    investor_universe_hints: str
    stage_fit_guidance: str
    sci_reg_guidance: str
    score_scientific_regulatory: bool


_PROFILE_CONFIGS: dict[str, _ProfileConfig] = {
    "therapeutic": _ProfileConfig(
        thesis_keywords=[],
        investor_universe_hints=(
            "Target investors active in drug discovery, biologic pipelines, and clinical-stage "
            "therapeutics. Include crossover funds, biotech-focused VCs (ARCH, Atlas, Foresite, "
            "OrbiMed, RA Capital), and CVC arms of large pharma."
        ),
        stage_fit_guidance=(
            "Stage fit reflects clinical development milestones: pre-IND, Phase 1/2/3, NDA/BLA readout."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects depth of expertise in the relevant therapeutic area, "
            "FDA pathway experience (IND, NDA, BLA, orphan designation), and clinical trial track record."
        ),
        score_scientific_regulatory=False,  # defers to needs_sci_reg() on thesis text
    ),
    "medical_device": _ProfileConfig(
        thesis_keywords=[
            "medtech hardware", "medical device innovation", "hospital capital equipment",
            "point-of-care workflow", "reusable medical devices", "cardiac monitoring",
            "FDA 510(k)", "510(k) exempt pathway", "clinical workflow efficiency",
            "hospital procurement", "device reimbursement",
        ],
        investor_universe_hints=(
            "Target medtech-focused VCs: Vensana Capital, Gilde Healthcare (device fund), "
            "MedTech Innovator ecosystem investors, hospital innovation funds, strategic device "
            "acquirers (Medtronic Ventures, J&J MedTech), and angels from AdvaMed / medtech exec "
            "networks. De-emphasize drug development VCs — different regulatory and commercial pathway."
        ),
        stage_fit_guidance=(
            "Stage fit reflects hardware development milestones: prototype, 510(k)/exempt submission, "
            "FDA clearance, commercial launch, hospital procurement pipeline maturity."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects FDA 510(k) or exempt pathway expertise, device "
            "classification knowledge, hospital procurement experience, and reimbursement code "
            "(CPT/HCPCS) strategy. Score positively for investors with device-specific regulatory "
            "portfolio companies."
        ),
        score_scientific_regulatory=True,
    ),
    "diagnostics": _ProfileConfig(
        thesis_keywords=[
            "in vitro diagnostics", "IVD", "LDT", "laboratory developed test", "CLIA",
            "specimen-to-result workflow", "molecular diagnostics", "point-of-care diagnostics",
            "lab automation", "clinical laboratory", "diagnostic assay",
        ],
        investor_universe_hints=(
            "Target Dx-focused VCs and strategics: Luminex/DiaSorin, bioMérieux, Roper Technologies, "
            "Becton Dickinson Ventures, Hologic, diagnostics-focused funds. Include crossover investors "
            "with IVD portfolio companies. De-emphasize therapeutic VCs who rarely lead Dx rounds."
        ),
        stage_fit_guidance=(
            "Stage fit reflects IVD/LDT development milestones: assay development, CLIA validation, "
            "EUA/510(k)/PMA submission, lab launch, reference lab partnerships, payer coverage."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects IVD regulatory pathway expertise (510(k), PMA, EUA, "
            "LDT framework), CLIA/CAP lab accreditation knowledge, and specimen-to-result workflow "
            "experience. Score positively for investors with diagnostics-specific portfolio depth."
        ),
        score_scientific_regulatory=True,
    ),
    "digital_health": _ProfileConfig(
        thesis_keywords=[
            "digital health", "health IT", "AI/ML in healthcare", "SaaS", "clinical workflow software",
            "electronic health records", "care coordination", "population health management",
            "value-based care", "health data interoperability", "FDA SaMD",
        ],
        investor_universe_hints=(
            "Target digital health VCs: General Catalyst (Health Assurance), 7wireVentures, Oak HC/FT, "
            "a16z bio (digital health portfolio), Rock Health, Bessemer Venture Partners (health IT), "
            "Define Ventures, Transformation Capital. Include strategic investors: Epic Ventures, "
            "health system innovation funds, and payer venture arms. De-emphasize drug development VCs."
        ),
        stage_fit_guidance=(
            "Stage fit reflects product-market fit milestones: pilot customers, health system "
            "contracts, ARR growth, net revenue retention, EHR integration depth, and payer/provider "
            "adoption rates. Clinical trial milestones are not primary signals."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects technology differentiation (AI/ML model performance, "
            "clinical validation studies, peer-reviewed publications) and clinical workflow adoption "
            "depth. For FDA Software as a Medical Device (SaMD): score 510(k)/De Novo expertise "
            "positively. For non-FDA SaaS: score based on EHR integration and outcomes evidence."
        ),
        score_scientific_regulatory=True,
    ),
    "service_cro": _ProfileConfig(
        thesis_keywords=[
            "CRO", "CDMO", "contract research organization", "contract development manufacturing",
            "lab services", "clinical operations", "bioanalytical services", "GMP manufacturing",
            "outsourced R&D", "clinical trial operations", "preclinical services",
        ],
        investor_universe_hints=(
            "Target service-company investors: Ampersand Capital (lab services), Sherbrooke Capital, "
            "Riverside Company (healthcare services), and strategic acquirers (ICON, Labcorp, IQVIA, "
            "Covance). Growth equity and PE investors who back services businesses with recurring "
            "contract revenue. VCs who back service businesses at scale (Warburg Pincus healthcare). "
            "De-emphasize early-stage biotech VCs who rarely lead services rounds."
        ),
        stage_fit_guidance=(
            "Stage fit reflects revenue maturity and contract pipeline: bookings backlog, contract "
            "renewal rate, customer concentration, capacity utilization, and EBITDA margin trajectory. "
            "Not clinical trial milestones."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects service differentiation and TAM defensibility: "
            "proprietary assay capabilities, GLP/GMP certifications, CLIA accreditation, FDA "
            "inspection track record, and unique scientific capabilities that create switching costs. "
            "Score positively for investors who back services businesses with regulatory moats."
        ),
        score_scientific_regulatory=True,
    ),
    "platform_tools": _ProfileConfig(
        thesis_keywords=[
            "enabling technology", "research tools", "platform scalability", "B2B scalability",
            "capital efficiency", "accelerate discovery", "lab infrastructure", "scientific instruments",
            "RUO", "research use only", "preclinical tools", "life science tools",
        ],
        investor_universe_hints=(
            "Target life science tools investors: Foresite Capital, RA Capital (tools portfolio), "
            "Northpond Ventures, Agilent Ventures, Illumina Ventures, Thermo Fisher Ventures. "
            "Include growth investors who back B2B SaaS for life sciences (Bessemer, Tiger Global). "
            "Strategic acquirers: Danaher, Thermo Fisher, Agilent, Bio-Techne. "
            "De-emphasize investors who only back clinical-stage therapeutics."
        ),
        stage_fit_guidance=(
            "Stage fit reflects B2B commercial traction: paying customers, ARR, net dollar retention, "
            "platform adoption across research institutions, and scalability of the core technology. "
            "RUO products do not require FDA clearance — commercial readiness is the primary signal."
        ),
        sci_reg_guidance=(
            "Scientific/regulatory fit reflects scientific domain alignment and commercial de-risking. "
            "RUO (Research Use Only) products have no FDA requirement — score this axis based on "
            "scientific credibility of the platform, publication record, and key opinion leader "
            "adoption. Faster time to revenue and lower burn vs. regulated pathways is a positive."
        ),
        score_scientific_regulatory=True,
    ),
}


# ---------------------------------------------------------------------------
# Modifier configs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ModifierConfig:
    keywords: list[str]
    guidance: str


_MODIFIER_CONFIGS: dict[str, _ModifierConfig] = {
    "ai_enabled": _ModifierConfig(
        keywords=[
            "AI/ML in healthcare", "FDA AI-enabled device", "machine learning clinical",
            "artificial intelligence healthcare", "predictive analytics clinical",
            "natural language processing EHR",
        ],
        guidance=(
            "AI/ML modifier: Weight investors with explicit AI-in-healthcare thesis. Include "
            "FDA AI/ML-based SaMD-focused funds. Highlight investors from the FDA AI-enabled "
            "device landscape (Khosla Ventures health AI, Google Ventures, Microsoft M12 health)."
        ),
    ),
    "rpm_saas": _ModifierConfig(
        keywords=[
            "RPM", "remote patient monitoring", "telehealth", "virtual care", "chronic disease management",
            "recurring revenue", "SaaS healthcare", "connected devices", "patient engagement platform",
        ],
        guidance=(
            "RPM/SaaS modifier: Weight investors who back recurring-revenue healthcare businesses. "
            "Include telehealth and RPM-focused funds: Bessemer (telehealth), American Well/Amwell "
            "strategic, Best Buy Health, Best Buy Health Fund. Weight ARR and net revenue retention "
            "as key metrics over clinical trial milestones."
        ),
    ),
    "cross_border_ca": _ModifierConfig(
        keywords=[
            "Canada", "Canadian healthcare", "cross-border health tech", "Health Canada",
        ],
        guidance=(
            "Cross-border Canada modifier: Boost Canadian VCs: BDC Capital ($150M Life Sciences Fund, "
            "launched April 2026), Genesys Capital, Lumira Ventures, Amplitude Ventures. Also boost "
            "US VCs with significant Canadian portfolio presence: ARCH Venture Partners, Atlas Venture, "
            "Frazier Healthcare Partners (US VCs in ~32% of Canadian deals). Score geographic alignment "
            "positively for investors operating across the US-Canada corridor."
        ),
    ),
    "ruo_no_reg": _ModifierConfig(
        keywords=[
            "research use only", "RUO", "preclinical", "capital efficient", "fast time to revenue",
        ],
        guidance=(
            "RUO/no-reg modifier: Reframe the scientific/regulatory axis positively. RUO products "
            "skip FDA clearance entirely — this is a capital efficiency feature, not a gap. "
            "Score scientific domain alignment and commercial de-risking positively. Reference: "
            "Vizgen $48M raise (ARCH Venture Partners + Northpond Ventures, Jan 2026) validated that "
            "RUO spatial genomics tools attract top-tier VCs without FDA pathway requirements. "
            "Weight investors who back capital-efficient tools businesses."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_scoring_instructions(
    profile: str,
    modifiers: list[str],
    classifier_version: str = _CLASSIFIER_VERSION,
) -> ScoringInstructions:
    """Build a ScoringInstructions config from client_profile + modifiers.

    Unknown profile falls back to 'therapeutic' to ensure safe behavior.
    Unknown modifiers are silently ignored (additive tolerance).
    """
    profile_cfg = _PROFILE_CONFIGS.get(profile)
    if profile_cfg is None:
        logger.warning("Unknown client_profile %r — falling back to 'therapeutic'", profile)
        profile_cfg = _PROFILE_CONFIGS["therapeutic"]

    all_modifier_keywords: list[str] = []
    modifier_guidance_parts: list[str] = []

    for mod in modifiers:
        mod_cfg = _MODIFIER_CONFIGS.get(mod)
        if mod_cfg is None:
            logger.warning("Unknown modifier %r — ignoring", mod)
            continue
        all_modifier_keywords.extend(mod_cfg.keywords)
        modifier_guidance_parts.append(mod_cfg.guidance)

    return ScoringInstructions(
        profile_type=profile,
        thesis_keywords=list(profile_cfg.thesis_keywords),
        investor_universe_hints=profile_cfg.investor_universe_hints,
        stage_fit_guidance=profile_cfg.stage_fit_guidance,
        sci_reg_guidance=profile_cfg.sci_reg_guidance,
        score_scientific_regulatory=profile_cfg.score_scientific_regulatory,
        modifier_keywords=all_modifier_keywords,
        modifier_guidance="\n".join(modifier_guidance_parts),
        classifier_version=classifier_version,
    )
