"""
NEWS/MACRO-1A: Macro event family registry.

Defines the canonical set of macro event families tracked by Trading OS.

TRADING_CAPABILITY = ZERO — this registry describes data families only.
No trading signals, entries, stops, or position sizes.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class MacroEventFamily(str, enum.Enum):
    """
    Canonical macro event family identifiers.

    These are data-family labels only.  They must NOT be interpreted as
    trade triggers (e.g. CPI_HOT => SHORT GOLD is explicitly prohibited).
    """

    # US Inflation
    CPI = "CPI"                      # Consumer Price Index (BLS)
    PPI = "PPI"                      # Producer Price Index (BLS)
    PCE = "PCE"                      # Personal Consumption Expenditures (BEA)

    # US Labour
    NFP = "NFP"                      # Non-Farm Payrolls (BLS)
    UNEMPLOYMENT = "UNEMPLOYMENT"    # Unemployment Rate (BLS)
    JOLTS = "JOLTS"                  # Job Openings and Labor Turnover Survey (BLS)
    ADP_EMPLOYMENT = "ADP_EMPLOYMENT"  # ADP National Employment Report

    # US Growth
    GDP = "GDP"                      # Gross Domestic Product (BEA)
    RETAIL_SALES = "RETAIL_SALES"    # Retail Sales (Census Bureau)
    ISM_MANUFACTURING = "ISM_MANUFACTURING"
    ISM_SERVICES = "ISM_SERVICES"

    # Federal Reserve / Monetary Policy
    FOMC = "FOMC"                    # FOMC rate decisions and statements
    FED_SPEECH = "FED_SPEECH"        # Federal Reserve speeches / testimony
    FOMC_MINUTES = "FOMC_MINUTES"    # Published FOMC meeting minutes

    # US Treasury
    TREASURY_2Y = "TREASURY_2Y"      # 2-year Treasury yield (daily official)
    TREASURY_5Y = "TREASURY_5Y"      # 5-year Treasury yield (daily official)
    TREASURY_10Y = "TREASURY_10Y"    # 10-year Treasury yield (daily official)
    TREASURY_30Y = "TREASURY_30Y"    # 30-year Treasury yield (daily official)
    TIPS_10Y = "TIPS_10Y"            # 10-year TIPS yield (real yield, daily official)

    # Dollar Index
    DXY = "DXY"
    # DXY = ICE U.S. Dollar Index ONLY.
    # Do NOT substitute: FRED broad trade-weighted dollar index, Federal Reserve
    # broad dollar index, synthetic FX basket, homemade EUR/JPY/GBP basket.
    # If no authorised DXY provider: DXY_STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED.

    # Breaking News
    BREAKING_NEWS = "BREAKING_NEWS"
    # Requires authorised point-in-time news provider.
    # If not configured: STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED.
    # Do NOT scrape and retrospectively reconstruct breaking news.


@dataclass(frozen=True)
class MacroEventFamilySpec:
    """
    Specification for a registered macro event family.

    Parameters
    ----------
    family:
        The canonical MacroEventFamily enum value.
    description:
        Human-readable description of what this family measures.
    primary_source_agency:
        Official releasing agency (e.g. "BLS", "BEA", "FOMC", "US_TREASURY").
    typical_release_frequency:
        Descriptive frequency (e.g. "monthly", "quarterly", "daily", "as_scheduled").
    unit:
        Unit of the primary value (e.g. "percent_yoy", "thousands_jobs").
    provider_status:
        Current implementation status: "IMPLEMENTED", "NOT_IMPLEMENTED", or
        "NOT_IMPLEMENTED_PROVIDER_REQUIRED".
    notes:
        Any important caveats or implementation notes.
    """

    family: MacroEventFamily
    description: str
    primary_source_agency: str
    typical_release_frequency: str
    unit: str
    provider_status: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Canonical registry
# ---------------------------------------------------------------------------

MACRO_EVENT_REGISTRY: dict[MacroEventFamily, MacroEventFamilySpec] = {
    MacroEventFamily.CPI: MacroEventFamilySpec(
        family=MacroEventFamily.CPI,
        description="US Consumer Price Index — headline and core, year-over-year and month-over-month.",
        primary_source_agency="BLS",
        typical_release_frequency="monthly",
        unit="percent_mom_or_yoy",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BLS Data API (api.bls.gov). Series: CUSR0000SA0 (headline), CUSR0000SA0L1E (core).",
    ),
    MacroEventFamily.PPI: MacroEventFamilySpec(
        family=MacroEventFamily.PPI,
        description="US Producer Price Index — final demand.",
        primary_source_agency="BLS",
        typical_release_frequency="monthly",
        unit="percent_mom_or_yoy",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BLS Data API. Series: WPSFD4.",
    ),
    MacroEventFamily.PCE: MacroEventFamilySpec(
        family=MacroEventFamily.PCE,
        description="US Personal Consumption Expenditures price index — the Fed's preferred inflation gauge.",
        primary_source_agency="BEA",
        typical_release_frequency="monthly",
        unit="percent_mom_or_yoy",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BEA API (apps.bea.gov/api). Table: T20804.",
    ),
    MacroEventFamily.NFP: MacroEventFamilySpec(
        family=MacroEventFamily.NFP,
        description="US Non-Farm Payrolls — total employees on non-farm payrolls.",
        primary_source_agency="BLS",
        typical_release_frequency="monthly",
        unit="thousands_jobs_mom",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BLS Data API. Series: CES0000000001.",
    ),
    MacroEventFamily.UNEMPLOYMENT: MacroEventFamilySpec(
        family=MacroEventFamily.UNEMPLOYMENT,
        description="US Unemployment Rate (U-3).",
        primary_source_agency="BLS",
        typical_release_frequency="monthly",
        unit="percent",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BLS Data API. Series: LNS14000000.",
    ),
    MacroEventFamily.JOLTS: MacroEventFamilySpec(
        family=MacroEventFamily.JOLTS,
        description="US Job Openings and Labor Turnover Survey.",
        primary_source_agency="BLS",
        typical_release_frequency="monthly",
        unit="thousands_openings",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BLS Data API. Series: JTS000000000000000JOL.",
    ),
    MacroEventFamily.ADP_EMPLOYMENT: MacroEventFamilySpec(
        family=MacroEventFamily.ADP_EMPLOYMENT,
        description="ADP National Employment Report — private sector employment change.",
        primary_source_agency="ADP",
        typical_release_frequency="monthly",
        unit="thousands_jobs_mom",
        provider_status="NOT_IMPLEMENTED",
        notes="Not an official government release. ADP Research Institute.",
    ),
    MacroEventFamily.GDP: MacroEventFamilySpec(
        family=MacroEventFamily.GDP,
        description="US Gross Domestic Product — advance, second, and third estimates.",
        primary_source_agency="BEA",
        typical_release_frequency="quarterly",
        unit="percent_annualized_qoq",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: BEA API. Table: T10101.",
    ),
    MacroEventFamily.RETAIL_SALES: MacroEventFamilySpec(
        family=MacroEventFamily.RETAIL_SALES,
        description="US Advance Retail Sales — monthly change.",
        primary_source_agency="US_CENSUS_BUREAU",
        typical_release_frequency="monthly",
        unit="percent_mom",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: Census Bureau. No public REST API; uses data files.",
    ),
    MacroEventFamily.ISM_MANUFACTURING: MacroEventFamilySpec(
        family=MacroEventFamily.ISM_MANUFACTURING,
        description="ISM Manufacturing PMI — diffusion index above 50 = expansion.",
        primary_source_agency="ISM",
        typical_release_frequency="monthly",
        unit="index_points",
        provider_status="NOT_IMPLEMENTED",
        notes="Institute for Supply Management. No direct public API.",
    ),
    MacroEventFamily.ISM_SERVICES: MacroEventFamilySpec(
        family=MacroEventFamily.ISM_SERVICES,
        description="ISM Services PMI — Services sector expansion/contraction.",
        primary_source_agency="ISM",
        typical_release_frequency="monthly",
        unit="index_points",
        provider_status="NOT_IMPLEMENTED",
        notes="Institute for Supply Management. No direct public API.",
    ),
    MacroEventFamily.FOMC: MacroEventFamilySpec(
        family=MacroEventFamily.FOMC,
        description="FOMC rate decisions, policy statements, and dot plot projections.",
        primary_source_agency="FEDERAL_RESERVE",
        typical_release_frequency="as_scheduled",
        unit="percent_target_rate",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: Federal Reserve website (federalreserve.gov). Approximately 8 meetings per year.",
    ),
    MacroEventFamily.FED_SPEECH: MacroEventFamilySpec(
        family=MacroEventFamily.FED_SPEECH,
        description="Federal Reserve official speeches, testimonies, and interviews.",
        primary_source_agency="FEDERAL_RESERVE",
        typical_release_frequency="as_scheduled",
        unit="N/A",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: federalreserve.gov/newsevents/speech. No NLP/hawkish-dovish in NEWS/MACRO-1A.",
    ),
    MacroEventFamily.FOMC_MINUTES: MacroEventFamilySpec(
        family=MacroEventFamily.FOMC_MINUTES,
        description="Published minutes of FOMC meetings (released approximately 3 weeks after meeting).",
        primary_source_agency="FEDERAL_RESERVE",
        typical_release_frequency="as_scheduled",
        unit="N/A",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: federalreserve.gov/monetarypolicy/fomccalendars.htm.",
    ),
    MacroEventFamily.TREASURY_2Y: MacroEventFamilySpec(
        family=MacroEventFamily.TREASURY_2Y,
        description="US 2-year Treasury constant maturity yield — daily official observation.",
        primary_source_agency="US_TREASURY",
        typical_release_frequency="daily",
        unit="percent_annualized",
        provider_status="NOT_IMPLEMENTED",
        notes=(
            "Source: US Treasury yield curve data (fiscaldata.treasury.gov or FRED series DGS2). "
            "These are DAILY_OFFICIAL observations. Do NOT call them 'live yields'."
        ),
    ),
    MacroEventFamily.TREASURY_5Y: MacroEventFamilySpec(
        family=MacroEventFamily.TREASURY_5Y,
        description="US 5-year Treasury constant maturity yield — daily official observation.",
        primary_source_agency="US_TREASURY",
        typical_release_frequency="daily",
        unit="percent_annualized",
        provider_status="NOT_IMPLEMENTED",
        notes=(
            "Source: fiscaldata.treasury.gov or FRED DGS5. "
            "Observation type: DAILY_OFFICIAL or STALE or CURRENT_OFFICIAL_OBSERVATION. "
            "Do NOT call these 'live yields'."
        ),
    ),
    MacroEventFamily.TREASURY_10Y: MacroEventFamilySpec(
        family=MacroEventFamily.TREASURY_10Y,
        description="US 10-year Treasury constant maturity yield — daily official observation.",
        primary_source_agency="US_TREASURY",
        typical_release_frequency="daily",
        unit="percent_annualized",
        provider_status="NOT_IMPLEMENTED",
        notes=(
            "Source: fiscaldata.treasury.gov or FRED DGS10. "
            "Do NOT call these 'live yields'. Label as DAILY_OFFICIAL/STALE/CURRENT_OFFICIAL_OBSERVATION."
        ),
    ),
    MacroEventFamily.TREASURY_30Y: MacroEventFamilySpec(
        family=MacroEventFamily.TREASURY_30Y,
        description="US 30-year Treasury constant maturity yield — daily official observation.",
        primary_source_agency="US_TREASURY",
        typical_release_frequency="daily",
        unit="percent_annualized",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: fiscaldata.treasury.gov or FRED DGS30.",
    ),
    MacroEventFamily.TIPS_10Y: MacroEventFamilySpec(
        family=MacroEventFamily.TIPS_10Y,
        description="US 10-year TIPS yield — real yield, daily official observation.",
        primary_source_agency="US_TREASURY",
        typical_release_frequency="daily",
        unit="percent_annualized",
        provider_status="NOT_IMPLEMENTED",
        notes="Source: FRED DFII10. Proxy for real interest rates relevant to gold/commodities.",
    ),
    MacroEventFamily.DXY: MacroEventFamilySpec(
        family=MacroEventFamily.DXY,
        description=(
            "ICE U.S. Dollar Index (DXY). "
            "MUST be the genuine ICE DXY. "
            "Do NOT substitute: FRED broad trade-weighted dollar index, "
            "Federal Reserve broad dollar index, synthetic FX basket, "
            "homemade EUR/JPY/GBP basket."
        ),
        primary_source_agency="ICE",
        typical_release_frequency="continuous_intraday",
        unit="index_points",
        provider_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
        notes=(
            "DXY_STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED. "
            "No authorised free public provider currently configured. "
            "Do NOT substitute any other index. "
            "Do NOT compute a synthetic basket."
        ),
    ),
    MacroEventFamily.BREAKING_NEWS: MacroEventFamilySpec(
        family=MacroEventFamily.BREAKING_NEWS,
        description="Real-time official breaking news from authorised point-in-time providers.",
        primary_source_agency="NOT_CONFIGURED",
        typical_release_frequency="as_published",
        unit="N/A",
        provider_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
        notes=(
            "STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED. "
            "No authorised point-in-time news provider configured. "
            "Do NOT scrape and retrospectively reconstruct breaking news from arbitrary websites."
        ),
    ),
}
