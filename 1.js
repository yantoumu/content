var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/worker.js
var accessTokenPromise = null;
var worker_default = {
  async fetch(request, env) {
    const { pathname, searchParams } = new URL(request.url);
    if (pathname !== "/api/keywords") {
      return json({ error: "Use /api/keywords" }, 404);
    }
    try {
      const keywords = splitCsv(searchParams.get("keyword"));
      const seedUrl = searchParams.get("url") || void 0;
      const geo = (searchParams.get("geo") || "GLOBAL").toUpperCase();
      const cid = searchParams.get("customerId") || "1961763003";
      const refresh = searchParams.get("refresh") === "true";
      if (!keywords.length && !seedUrl) return json({ error: "keyword or url param required" }, 400);
      if (keywords.length > 10) return json({ error: "max 10 keywords" }, 400);
      if (geo !== "GLOBAL") return json({ error: `unsupported geo ${geo}` }, 400);
      const cacheKey = buildCacheKey({ cid, keywords, seedUrl, geo });
      if (!refresh) {
        const cached = await env.RESULTS_CACHE.get(cacheKey, { type: "json" });
        if (cached) {
          debug(env, "RESULTS_CACHE hit");
          return json(cached);
        }
      } else {
        debug(env, "refresh=true, skipping cache");
      }
      const token = await getAccessToken(env);
      const resp = await fetchKeywordIdeas({ env, token, cid, keywords, seedUrl });
      const formatted = transform(resp, keywords);
      const payload = {
        status: "success",
        geo_target: geo,
        total_results: formatted.length,
        data: formatted
      };
      await maybeCacheResults(env, cacheKey, payload);
      return json(payload);
    } catch (e) {
      console.error("[worker]", e);
      return json({ error: `${e.name}: ${e.message}` }, 500);
    }
  }
};
async function getAccessToken(env) {
  const kvHit = await env.TOKEN_CACHE.get("google_token", { type: "json" });
  if (kvHit && kvHit.expires > Date.now()) return kvHit.token;
  if (!accessTokenPromise) {
    debug(env, "refreshing Google token");
    accessTokenPromise = refreshToken(env).finally(() => {
      accessTokenPromise = null;
    });
  }
  return accessTokenPromise;
}
__name(getAccessToken, "getAccessToken");
async function refreshToken(env) {
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      refresh_token: env.GOOGLE_REFRESH_TOKEN,
      grant_type: "refresh_token"
    })
  });
  if (!r.ok) throw new Error(`OAuth ${r.status}`);
  const { access_token: token, expires_in } = await r.json();
  const ttl = expires_in - 60;
  await env.TOKEN_CACHE.put("google_token", JSON.stringify({ token, expires: Date.now() + ttl * 1e3 }), { expirationTtl: ttl });
  return token;
}
__name(refreshToken, "refreshToken");
async function fetchKeywordIdeas({ env, token, cid, keywords, seedUrl }) {
  const url = `https://googleads.googleapis.com/v18/customers/${cid}:generateKeywordIdeas`;
  const body = {
    language: "languageConstants/1000",
    keyword_plan_network: "GOOGLE_SEARCH",
    page_size: 1e4
  };
  if (keywords.length && seedUrl) body.keyword_and_url_seed = { keywords, url: seedUrl };
  else if (keywords.length) body.keyword_seed = { keywords };
  else if (seedUrl) body.url_seed = { url: seedUrl };
  const r = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "developer-token": env.GOOGLE_DEVELOPER_TOKEN,
      "login-customer-id": env.GOOGLE_LOGIN_CUSTOMER_ID,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`Ads API ${r.status}`);
  return r.json();
}
__name(fetchKeywordIdeas, "fetchKeywordIdeas");
async function maybeCacheResults(env, key, payload) {
  const BYTES = new TextEncoder().encode(JSON.stringify(payload)).length;
  const MAX_OBJ = 10 * 1024;
  if (BYTES > MAX_OBJ) {
    debug(env, "skip cache \u2013 object too big");
    return;
  }
  const CAP = parseInt(env.KV_WRITE_CAP || "900", 10);
  const day = (/* @__PURE__ */ new Date()).toISOString().slice(0, 10).replace(/-/g, "");
  const counterKey = `__wc__${day}`;
  let count = parseInt(await env.RESULTS_CACHE.get(counterKey) || "0", 10);
  if (count >= CAP) {
    debug(env, "skip cache \u2013 daily cap reached");
    return;
  }
  await env.RESULTS_CACHE.put(key, JSON.stringify(payload), { expirationTtl: 60 * 60 * 12 });
  await env.RESULTS_CACHE.put(counterKey, String(count + 1), { expirationTtl: 60 * 60 * 24 });
}
__name(maybeCacheResults, "maybeCacheResults");
function transform(g, filter) {
  const filt = new Set(filter.map((k) => k.toLowerCase()));
  const monthMap = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12
  };
  return (g.results || []).filter((it) => !filt.size || filt.has(it.text.toLowerCase())).map((it) => {
    const m = it.keywordIdeaMetrics || {};
    const vols = m.monthlySearchVolumes || [];
    const arr = vols.map((v) => ({
      \u5E74: parseInt(v.year) || 0,
      \u6708: monthMap[v.month] || 0,
      searches: +v.monthlySearches || 0
    }));
    const latest = arr.at(-1)?.searches || 0;
    const max = arr.reduce((mx, v) => Math.max(mx, v.searches), 0);
    const dataQuality = analyzeDataQuality(arr);
    return {
      keyword: it.text,
      metrics: {
        avg_monthly_searches: +m.avgMonthlySearches || 0,
        latest_searches: latest,
        max_monthly_searches: max,
        competition: m.competition ?? "N/A",
        competition_index: m.competitionIndex ? +m.competitionIndex : null,
        low_top_of_page_bid_micros: m.lowTopOfPageBidMicros ? +m.lowTopOfPageBidMicros : null,
        high_top_of_page_bid_micros: m.highTopOfPageBidMicros ? +m.highTopOfPageBidMicros : null,
        monthly_searches: arr,
        data_quality: dataQuality
      }
    };
  }).sort((a, b) => b.metrics.avg_monthly_searches - a.metrics.avg_monthly_searches);
}
__name(transform, "transform");
function analyzeDataQuality(monthlyData) {
  if (!monthlyData.length) {
    return {
      status: "no_data",
      complete: false,
      has_missing_months: false,
      only_last_month_has_data: false,
      total_months: 0,
      available_months: 0,
      missing_months_count: 0,
      missing_months: [],
      warnings: ["no_monthly_data"]
    };
  }
  const sorted = monthlyData.sort((a, b) => {
    if (a.\u5E74 !== b.\u5E74) return a.\u5E74 - b.\u5E74;
    return a.\u6708 - b.\u6708;
  });
  const warnings = [];
  const nonZeroData = sorted.filter((item) => item.searches > 0);
  const zeroData = sorted.filter((item) => item.searches === 0);
  const onlyLastMonthHasData = nonZeroData.length === 1 && nonZeroData[0] === sorted[sorted.length - 1];
  if (onlyLastMonthHasData) {
    warnings.push("only_last_month_has_data");
  }
  const hasMissingMonths = zeroData.length > 0;
  if (hasMissingMonths) {
    warnings.push("has_missing_months");
  }
  const isComplete = warnings.length === 0;
  return {
    status: isComplete ? "complete" : "incomplete",
    complete: isComplete,
    has_missing_months: hasMissingMonths,
    only_last_month_has_data: onlyLastMonthHasData,
    total_months: sorted.length,
    available_months: nonZeroData.length,
    missing_months_count: zeroData.length,
    missing_months: zeroData.map((item) => ({ year: item.\u5E74, month: item.\u6708 })),
    warnings
  };
}
__name(analyzeDataQuality, "analyzeDataQuality");
function splitCsv(raw) {
  return raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
}
__name(splitCsv, "splitCsv");
function buildCacheKey({ cid, keywords, seedUrl, geo }) {
  const kwPart = keywords.join("|");
  return `${cid}:${geo}:${kwPart}:${seedUrl || ""}`.slice(0, 480);
}
__name(buildCacheKey, "buildCacheKey");
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=UTF-8",
      "Access-Control-Allow-Origin": "*"
    }
  });
}
__name(json, "json");
function debug(env, ...args) {
  if (env.DEBUG || typeof env.DEBUG === "string" && env.DEBUG.toLowerCase() === "true") console.log("[debug]", ...args);
}
__name(debug, "debug");
export {
  worker_default as default
};
//# sourceMappingURL=worker.js.map
