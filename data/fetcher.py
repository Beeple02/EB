"""
Fetches equity data from EODHD (primary) with yfinance fallback.
All public functions return plain dicts; missing values are None.
"""

import sys
import requests
from datetime import datetime

from config import EODHD_API_KEY, EODHD_BASE_URL


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe(value, default=None):
    """Return value if it is not None/empty/zero-length string, else default."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() in ("", "None", "N/A", "null"):
        return default
    return value


def _eodhd_get(path, params=None):
    """
    GET {EODHD_BASE_URL}/{path} with api_token injected.
    Returns (parsed_json_or_None, http_status_code).
    """
    if not EODHD_API_KEY:
        return None, 0
    p = dict(params or {})
    p["api_token"] = EODHD_API_KEY
    p["fmt"] = "json"
    try:
        r = requests.get(f"{EODHD_BASE_URL}/{path}", params=p, timeout=20)
        if r.ok:
            return r.json(), r.status_code
        return None, r.status_code
    except Exception as exc:
        print(f"EODHD request error: {exc}", file=sys.stderr)
        return None, 0


def _quota_exceeded(status_code):
    return status_code in (402, 429)


# ---------------------------------------------------------------------------
# EODHD parsers
# ---------------------------------------------------------------------------

def _parse_snapshot_eodhd(fund, realtime):
    h = fund.get("Highlights") or {}
    v = fund.get("Valuation") or {}
    t = fund.get("Technicals") or {}

    price = None
    if realtime:
        price = _safe(realtime.get("close")) or _safe(realtime.get("adjusted_close"))
    if price is None:
        price = _safe(h.get("WallStreetTargetPrice"))  # last resort placeholder

    return {
        "current_price": price,
        "market_cap": _safe(h.get("MarketCapitalization")),
        "pe_ratio": _safe(h.get("PERatio")),
        "ev_ebitda": _safe(v.get("EnterpriseValueEbitda")),
        "ps_ratio": _safe(v.get("PriceSalesTTM")),
        "pb_ratio": _safe(v.get("PriceBookMRQ")),
        "week52_high": _safe(t.get("52WeekHigh")),
        "week52_low": _safe(t.get("52WeekLow")),
    }


def _parse_earnings_eodhd(fund):
    """
    Return last 4 quarters of revenue, net income, EPS actual/estimate, YoY growth.
    Cross-references Financials.Income_Statement.quarterly with Earnings.History.
    """
    income_q = (
        (fund.get("Financials") or {})
        .get("Income_Statement") or {}
    ).get("quarterly") or {}

    earnings_hist = (fund.get("Earnings") or {}).get("History") or {}

    # Sort quarters descending
    sorted_dates = sorted(income_q.keys(), reverse=True)[:8]  # 8 to compute YoY

    quarters = []
    for date_str in sorted_dates[:4]:
        row = income_q[date_str]
        rev = _safe(row.get("totalRevenue"))
        ni = _safe(row.get("netIncome"))

        # EPS from Earnings.History (key is period-end date)
        eh = earnings_hist.get(date_str) or {}
        eps_actual = _safe(eh.get("epsActual"))
        eps_estimate = _safe(eh.get("epsEstimate"))

        # YoY: find same quarter one year back
        try:
            period_dt = datetime.strptime(date_str, "%Y-%m-%d")
            yoy_candidates = [
                d for d in sorted_dates[4:]
                if abs((datetime.strptime(d, "%Y-%m-%d") - period_dt).days - 365) <= 45
            ]
            yoy_row = income_q[yoy_candidates[0]] if yoy_candidates else None
        except (ValueError, IndexError):
            yoy_row = None

        rev_yoy = None
        ni_yoy = None
        if yoy_row and rev is not None:
            prev_rev = _safe(yoy_row.get("totalRevenue"))
            if prev_rev and float(prev_rev) != 0:
                rev_yoy = (float(rev) - float(prev_rev)) / abs(float(prev_rev)) * 100
        if yoy_row and ni is not None:
            prev_ni = _safe(yoy_row.get("netIncome"))
            if prev_ni and float(prev_ni) != 0:
                ni_yoy = (float(ni) - float(prev_ni)) / abs(float(prev_ni)) * 100

        quarters.append(
            {
                "period": date_str,
                "revenue": float(rev) if rev is not None else None,
                "net_income": float(ni) if ni is not None else None,
                "eps_actual": float(eps_actual) if eps_actual is not None else None,
                "eps_estimate": float(eps_estimate) if eps_estimate is not None else None,
                "revenue_yoy": rev_yoy,
                "net_income_yoy": ni_yoy,
            }
        )
    return quarters


def _parse_margins_eodhd(fund):
    """Return last 3 fiscal years of gross/operating/net margins."""
    income_y = (
        (fund.get("Financials") or {})
        .get("Income_Statement") or {}
    ).get("yearly") or {}

    sorted_years = sorted(income_y.keys(), reverse=True)[:3]
    margins = []
    for date_str in sorted_years:
        row = income_y[date_str]
        rev = _safe(row.get("totalRevenue"))
        gp = _safe(row.get("grossProfit"))
        oi = _safe(row.get("operatingIncome"))
        ni = _safe(row.get("netIncome"))

        def pct(num, denom):
            try:
                return float(num) / float(denom) * 100 if num and denom and float(denom) != 0 else None
            except (TypeError, ValueError):
                return None

        margins.append(
            {
                "period": date_str[:4],
                "gross_margin": pct(gp, rev),
                "operating_margin": pct(oi, rev),
                "net_margin": pct(ni, rev),
            }
        )
    return margins


def _parse_analyst_eodhd(fund, current_price):
    ar = fund.get("AnalystRatings") or {}
    strong_buy = int(_safe(ar.get("StrongBuy"), 0) or 0)
    buy = int(_safe(ar.get("Buy"), 0) or 0)
    hold = int(_safe(ar.get("Hold"), 0) or 0)
    sell = int(_safe(ar.get("Sell"), 0) or 0)
    strong_sell = int(_safe(ar.get("StrongSell"), 0) or 0)

    target = _safe(ar.get("TargetPrice"))
    target = float(target) if target is not None else None

    upside = None
    if target is not None and current_price:
        try:
            upside = (target - float(current_price)) / abs(float(current_price)) * 100
        except (TypeError, ValueError):
            pass

    return {
        "buy": strong_buy + buy,
        "hold": hold,
        "sell": sell + strong_sell,
        "median_price_target": target,
        "upside_pct": upside,
    }


def _parse_news_eodhd(news_list):
    catalysts = []
    for item in (news_list or [])[:5]:
        date_raw = item.get("date") or ""
        date_str = date_raw[:10] if date_raw else None
        headline = _safe(item.get("title"))
        if headline:
            catalysts.append({"date": date_str, "headline": headline})
    return catalysts


# ---------------------------------------------------------------------------
# yfinance fallback
# ---------------------------------------------------------------------------

def _fetch_yfinance(ticker):
    """Full data pull from yfinance. Returns same structure as EODHD path."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed; cannot fall back.", file=sys.stderr)
        return _empty_data()

    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    # Snapshot
    snapshot = {
        "current_price": _safe(info.get("currentPrice")) or _safe(info.get("regularMarketPrice")),
        "market_cap": _safe(info.get("marketCap")),
        "pe_ratio": _safe(info.get("trailingPE")),
        "ev_ebitda": _safe(info.get("enterpriseToEbitda")),
        "ps_ratio": _safe(info.get("priceToSalesTrailing12Months")),
        "pb_ratio": _safe(info.get("priceToBook")),
        "week52_high": _safe(info.get("fiftyTwoWeekHigh")),
        "week52_low": _safe(info.get("fiftyTwoWeekLow")),
    }

    # Earnings / income quarterly
    earnings_data = []
    try:
        qincome = t.quarterly_income_stmt
        qearnings = t.quarterly_earnings if hasattr(t, "quarterly_earnings") else None

        if qincome is not None and not qincome.empty:
            cols = list(qincome.columns)[:4]
            all_cols = list(qincome.columns)

            def _val(df, row_label, col):
                try:
                    v = df.loc[row_label, col]
                    return float(v) if v is not None and str(v) != "nan" else None
                except Exception:
                    return None

            for col in cols:
                date_str = str(col)[:10]
                rev = _val(qincome, "Total Revenue", col)
                ni = _val(qincome, "Net Income", col)

                # YoY: same quarter previous year
                rev_yoy = None
                ni_yoy = None
                try:
                    idx = all_cols.index(col)
                    if idx + 4 < len(all_cols):
                        yoy_col = all_cols[idx + 4]
                        prev_rev = _val(qincome, "Total Revenue", yoy_col)
                        prev_ni = _val(qincome, "Net Income", yoy_col)
                        if prev_rev and prev_rev != 0 and rev is not None:
                            rev_yoy = (rev - prev_rev) / abs(prev_rev) * 100
                        if prev_ni and prev_ni != 0 and ni is not None:
                            ni_yoy = (ni - prev_ni) / abs(prev_ni) * 100
                except Exception:
                    pass

                # EPS
                eps_actual = None
                eps_estimate = None
                if qearnings is not None and not qearnings.empty:
                    try:
                        eps_actual = float(qearnings.loc[col, "EPS"])
                    except Exception:
                        pass

                earnings_data.append(
                    {
                        "period": date_str,
                        "revenue": rev,
                        "net_income": ni,
                        "eps_actual": eps_actual,
                        "eps_estimate": eps_estimate,
                        "revenue_yoy": rev_yoy,
                        "net_income_yoy": ni_yoy,
                    }
                )
    except Exception as exc:
        print(f"yfinance earnings error: {exc}", file=sys.stderr)

    # Margins (yearly)
    margins_data = []
    try:
        yincome = t.income_stmt
        if yincome is not None and not yincome.empty:
            ycols = list(yincome.columns)[:3]

            def _yval(row_label, col):
                try:
                    v = yincome.loc[row_label, col]
                    return float(v) if v is not None and str(v) != "nan" else None
                except Exception:
                    return None

            for col in ycols:
                rev = _yval("Total Revenue", col)
                gp = _yval("Gross Profit", col)
                oi = _yval("Operating Income", col)
                ni = _yval("Net Income", col)

                def pct(num, denom):
                    try:
                        return num / abs(denom) * 100 if num and denom and denom != 0 else None
                    except Exception:
                        return None

                margins_data.append(
                    {
                        "period": str(col)[:4],
                        "gross_margin": pct(gp, rev),
                        "operating_margin": pct(oi, rev),
                        "net_margin": pct(ni, rev),
                    }
                )
    except Exception as exc:
        print(f"yfinance margins error: {exc}", file=sys.stderr)

    # Analyst
    analyst_data = {
        "buy": None,
        "hold": None,
        "sell": None,
        "median_price_target": _safe(info.get("targetMedianPrice")),
        "upside_pct": None,
    }
    try:
        price = snapshot["current_price"]
        target = analyst_data["median_price_target"]
        if price and target:
            analyst_data["upside_pct"] = (float(target) - float(price)) / abs(float(price)) * 100
    except Exception:
        pass

    try:
        recs = t.recommendations
        if recs is not None and not recs.empty:
            latest = recs.iloc[-20:]
            col_lower = {c.lower(): c for c in latest.columns}
            def _sum_col(name):
                c = col_lower.get(name)
                return int(latest[c].sum()) if c else 0
            analyst_data["buy"] = _sum_col("strongbuy") + _sum_col("buy")
            analyst_data["hold"] = _sum_col("hold")
            analyst_data["sell"] = _sum_col("sell") + _sum_col("strongsell")
    except Exception:
        pass

    # News
    catalysts = []
    try:
        raw_news = t.news or []
        for item in raw_news[:5]:
            ts = item.get("providerPublishTime")
            date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else None
            headline = _safe(item.get("title"))
            if headline:
                catalysts.append({"date": date_str, "headline": headline})
    except Exception as exc:
        print(f"yfinance news error: {exc}", file=sys.stderr)

    return {
        "snapshot": snapshot,
        "earnings": earnings_data,
        "margins": margins_data,
        "analyst": analyst_data,
        "catalysts": catalysts,
        "source": "yfinance",
    }


def _empty_data():
    return {
        "snapshot": {k: None for k in ("current_price", "market_cap", "pe_ratio", "ev_ebitda", "ps_ratio", "pb_ratio", "week52_high", "week52_low")},
        "earnings": [],
        "margins": [],
        "analyst": {"buy": None, "hold": None, "sell": None, "median_price_target": None, "upside_pct": None},
        "catalysts": [],
        "source": "none",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_all(ticker: str) -> dict:
    """
    Fetch all data for *ticker*.
    Returns a dict with keys: ticker, snapshot, earnings, margins, analyst, catalysts, source.
    """
    result = {"ticker": ticker}

    # --- Fundamentals (EODHD) ---
    fund, fund_status = _eodhd_get(f"fundamentals/{ticker}")

    if _quota_exceeded(fund_status):
        print(
            f"Warning: EODHD quota exceeded (HTTP {fund_status}). Falling back to yfinance.",
            file=sys.stderr,
        )
        result.update(_fetch_yfinance(ticker))
        return result

    if fund is None:
        print(
            "Warning: EODHD fundamentals unavailable. Falling back to yfinance.",
            file=sys.stderr,
        )
        result.update(_fetch_yfinance(ticker))
        return result

    # --- Real-time quote (EODHD) ---
    realtime, rt_status = _eodhd_get(f"real-time/{ticker}")
    if _quota_exceeded(rt_status):
        print(
            f"Warning: EODHD real-time quota exceeded (HTTP {rt_status}). Falling back to yfinance.",
            file=sys.stderr,
        )
        result.update(_fetch_yfinance(ticker))
        return result

    snapshot = _parse_snapshot_eodhd(fund, realtime)
    result["snapshot"] = snapshot
    result["earnings"] = _parse_earnings_eodhd(fund)
    result["margins"] = _parse_margins_eodhd(fund)
    result["analyst"] = _parse_analyst_eodhd(fund, snapshot.get("current_price"))
    result["source"] = "eodhd"

    # --- News (EODHD) ---
    news, news_status = _eodhd_get("news", {"s": ticker, "limit": 5, "offset": 0})
    if _quota_exceeded(news_status) or news is None:
        if _quota_exceeded(news_status):
            print(
                f"Warning: EODHD news quota exceeded (HTTP {news_status}). Falling back to yfinance for news.",
                file=sys.stderr,
            )
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            raw_news = t.news or []
            catalysts = []
            for item in raw_news[:5]:
                ts = item.get("providerPublishTime")
                date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else None
                headline = _safe(item.get("title"))
                if headline:
                    catalysts.append({"date": date_str, "headline": headline})
            result["catalysts"] = catalysts
        except Exception:
            result["catalysts"] = []
    else:
        result["catalysts"] = _parse_news_eodhd(news)

    return result
