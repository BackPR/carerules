/* CareRules API: the only server part of the Handbook Inspector. It keeps the Beam token secret, runs a check only
   with a valid access code, accepts only CareRules inspection prompts, and keeps spending inside hard dollar limits
   (per code, per day, in total) held in one Durable Object, so parallel requests can't slip past them. Replies are
   cached for 7 days so the same request never costs twice. Everything else (reading the handbook, choosing rule
   pages, building the prompt, checking every quote, the report) runs in the visitor's browser. */
import { DurableObject } from "cloudflare:workers";

export interface Env {
  HF_TOKEN: string; // Hugging Face token with "Make calls to Inference Providers"
  ACCESS_CODES: string; // JSON: {"CODE": {"per_day": 1, "max_states": 3, "usd_day": 2}, ...}
  KV: KVNamespace; // reply cache only
  ASSETS: Fetcher; // the page, served on care.backpr.com
  BUDGET: DurableObjectNamespace<Budget>;
  RL?: RateLimit;
  DAILY_USD?: string; // codes without their own usd_day, together, per UTC day
  TOTAL_USD?: string; // every code together, ever
  LIVE_OFF?: string; // "1" pauses live checks
  DEMO_USD?: string; // the no-code sample-handbook checks, together, per UTC day
}

const MODEL = "reflection/Beam-1.0-501B-A23B:baseten"; // provider pinned so routing and prices can't drift
const ROUTER = "https://router.huggingface.co/v1/chat/completions";
const PRICE_IN = 0.4, PRICE_OUT = 1.2; // USD per million tokens (Baseten via Hugging Face)
const MAX_OUT = { low: 24576, high: 49152 }; // reasoning tokens count here too
const MAX_PROMPT = 420_000, MAX_HANDBOOK = 300_000; // the page sends up to 240k characters of handbook, plus page labels
const CALLS_PER_CHECK = 32; // up to 6 states x checklist parts (16 at most), each retried once
const ORIGINS = new Set(["https://care.backpr.com", "https://backpr-carerules-inspector.static.hf.space", "http://localhost:7861"]);
const INSTRUCTIONS = "You are a careful licensing inspector. Audit the handbook against the checklist and the rulebook above.";
const PART = "\nFor this part, leave extra_conflicts empty.";
// SHA-256 of the page's fixed instruction block (from "You are a careful..." to the end); scripts/parity.js checks it.
const INSTRUCTIONS_SHA = "f09e8d14a3ae7c1c26272f2d5ba7a59995d710c36e8ccb23a3633179420c6d13";
const PAUSED = "Live checks are paused right now. The sample reports still work.";
const RESETS = "It resets every day at midnight UTC (late afternoon in the US).";

type Rule = { per_day?: number; max_states?: number; usd_day?: number; pool?: string; pool_usd?: number; calls?: number };
type Verdict = { ok: boolean; why?: "code" | "calls" | "states" | "code_budget" | "budget" | "total"; day: string };
// No code needed for a sample handbook with a small edit ("plant a mistake"): one state, Standard, a few a day per
// visitor, from its own small daily pool so it can't use up anyone else's checks.
const DEMO_EDIT = 1500; // characters that may differ from the sample handbook
const demoRule = (env: Env): Rule => ({ per_day: 3, max_states: 1, pool: "demo", pool_usd: Number(env.DEMO_USD || 1), calls: 10 });
const DEMO_PROMPT = 220_000; // the largest sample-handbook prompt is about 177k characters
const CODE_RE = /^[A-Z]+-[A-Z]+-[A-Z0-9]{6,}$/;
// A Map, not a plain object: "constructor", "__proto__" and friends must never count as codes.
const codes = (env: Env): Map<string, Rule> => {
  try { return new Map(Object.entries(JSON.parse(env.ACCESS_CODES || "{}"))) as Map<string, Rule>; } catch { return new Map(); }
};
const ruleFor = (env: Env, code: string): Rule | undefined => (CODE_RE.test(code) ? codes(env).get(code) : undefined);
const day = () => new Date().toISOString().slice(0, 10);
// The shared daily pot a rule spends from: its own pool, everyone's (codes without usd_day), or none (judges' usd_day).
const poolKey = (rule: Rule, d: string) => (rule.pool ? `usd:pool:${rule.pool}:${d}` : rule.usd_day === undefined ? `usd:${d}` : null);

/* One instance ("global") holds every counter; a Durable Object runs one request at a time, so each reservation
   is atomic. Spending is reserved before the call (an estimate) and settled after it (the real cost). */
export class Budget extends DurableObject<Env> {
  async left(code: string, perDay: number) {
    const checks = (await this.ctx.storage.get<string[]>(`checks:${code}:${day()}`)) || [];
    return Math.max(0, perDay - checks.length);
  }

  /* Once a day, drop counters older than two days (they hold scrambled visitor keys); the lifetime total stays. */
  async tidy(d: string) {
    const s = this.ctx.storage;
    if ((await s.get<string>("meta:tidied")) === d) return;
    const cutoff = new Date(Date.parse(d) - 2 * 86400_000).toISOString().slice(0, 10);
    const old = [...(await s.list()).keys()].filter((k) => { const m = k.match(/(\d{4}-\d{2}-\d{2})/); return !!m && m[1] < cutoff; });
    for (let i = 0; i < old.length; i += 128) await s.delete(old.slice(i, i + 128));
    await s.put("meta:tidied", d);
  }

  async reserve(code: string, check: string, state: string, rule: Rule, est: number, dailyUsd: number, totalUsd: number): Promise<Verdict> {
    const s = this.ctx.storage, d = day(), pool = poolKey(rule, d), no = (why: Verdict["why"]): Verdict => ({ ok: false, why, day: d });
    await this.tidy(d);
    const checks = (await s.get<string[]>(`checks:${code}:${d}`)) || [];
    const calls = (await s.get<number>(`calls:${code}:${d}:${check}`)) || 0;
    const states = (await s.get<string[]>(`states:${code}:${d}:${check}`)) || [];
    const codeUsd = (await s.get<number>(`usd:${code}:${d}`)) || 0;
    const poolUsd = pool ? (await s.get<number>(pool)) || 0 : 0;
    const allUsd = (await s.get<number>("usd:all")) || 0;
    const isNew = !checks.includes(check);
    if (isNew && checks.length >= (rule.per_day ?? 1)) return no("code");
    if (calls >= (rule.calls ?? CALLS_PER_CHECK)) return no("calls");
    if (!states.includes(state) && states.length >= (rule.max_states ?? 3)) return no("states");
    // A code with its own daily dollars (the judges') doesn't share, or use up, everyone else's, and the lifetime cap
    // (which protects the credit for them) doesn't apply to it.
    if (rule.usd_day !== undefined && codeUsd + est > rule.usd_day) return no("code_budget");
    if (pool && poolUsd + est > (rule.pool ? rule.pool_usd ?? 0 : dailyUsd)) return no("budget");
    if (pool && allUsd + est > totalUsd) return no("total");
    if (isNew) checks.push(check);
    if (!states.includes(state)) states.push(state);
    await s.put({ [`checks:${code}:${d}`]: checks, [`calls:${code}:${d}:${check}`]: calls + 1, [`states:${code}:${d}:${check}`]: states,
      [`usd:${code}:${d}`]: codeUsd + est, ...(pool ? { [pool]: poolUsd + est } : {}), "usd:all": allUsd + est });
    return { ok: true, day: d };
  }

  /* After the call: charge the real cost instead of the estimate. A call that never reached Beam is refunded and doesn't
     count, and a check whose every call failed doesn't use up the code. `d` is the reservation's day. */
  async settle(code: string, check: string, rule: Rule, d: string, est: number, real: number, refund: boolean) {
    const s = this.ctx.storage, pool = poolKey(rule, d);
    const keys = [`usd:${code}:${d}`, "usd:all", ...(pool ? [pool] : [])];
    const now = await s.get<number>(keys);
    const put: Record<string, unknown> = {};
    for (const k of keys) put[k] = Math.max(0, (now.get(k) || 0) + (refund ? 0 : real) - est);
    if (refund) {
      const calls = Math.max(0, ((await s.get<number>(`calls:${code}:${d}:${check}`)) || 1) - 1);
      put[`calls:${code}:${d}:${check}`] = calls;
      if (calls === 0) put[`checks:${code}:${d}`] = ((await s.get<string[]>(`checks:${code}:${d}`)) || []).filter((c) => c !== check);
    }
    await s.put(put);
  }

  async spent() {
    const s = this.ctx.storage, d = day();
    return { codes_today: (await s.get<number>(`usd:${d}`)) || 0, demo_today: (await s.get<number>(`usd:pool:demo:${d}`)) || 0,
      total: (await s.get<number>("usd:all")) || 0 };
  }
}

function cors(req: Request): Record<string, string> {
  const origin = req.headers.get("Origin") || "";
  return ORIGINS.has(origin)
    ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", Vary: "Origin" }
    : {};
}
const json = (req: Request, data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...cors(req) } });

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/* Only CareRules inspection prompts, as the page builds them: rule pages, checklist, handbook, then exactly the fixed
   instructions (checked by hash), so nothing can be added after them. */
async function isInspection(prompt: string): Promise<boolean> {
  if (!/^=== RULEBOOK [A-Z]{2}: /.test(prompt)) return false;
  const list = prompt.indexOf("\n\n=== CHECKLIST for "), hb = prompt.indexOf("\n\n=== THE CENTER'S HANDBOOK ===\n");
  const ins = prompt.lastIndexOf("\n\n" + INSTRUCTIONS + "\n");
  if (list < 0 || hb < list || ins < hb || ins - hb > MAX_HANDBOOK) return false;
  const tail = prompt.slice(ins + 2);
  return (await sha256(tail.endsWith(PART) ? tail.slice(0, -PART.length) : tail)) === INSTRUCTIONS_SHA;
}

/* Beam's answer is worth caching only if it can be read: a JSON object with a list of items. */
function readable(content: string): boolean {
  const tryParse = (t: string) => { try { const g = JSON.parse(t); return !!g && Array.isArray(g.items) && g.items.length > 0; } catch { return false; } };
  const text = content.trim(), a = text.indexOf("{"), b = text.lastIndexOf("}");
  return tryParse(text) || (a >= 0 && b > a && tryParse(text.slice(a, b + 1))) ||
    [...text.matchAll(/```(?:json)?\s*([\s\S]*?)```/g)].some((m) => tryParse(m[1]));
}

/* A no-code check must be one of our sample handbooks with one small edit, checked against its own state. */
async function demoProblem(env: Env, req: Request, prompt: string, effort: string): Promise<string> {
  const own = "Without a code, you can check a sample handbook against its own state, at Standard.";
  const state = (prompt.match(/^=== RULEBOOK ([A-Z]{2}): /) || [])[1];
  if (effort !== "low" || !state || prompt.length > DEMO_PROMPT) return own;
  const res = await env.ASSETS.fetch(new Request(new URL(`/samples/eval/${state}/clean.md`, req.url)));
  if (!res.ok) return own;
  const start = prompt.indexOf("\n\n=== THE CENTER'S HANDBOOK ===\n"), end = prompt.lastIndexOf("\n\n" + INSTRUCTIONS + "\n");
  const flat = (t: string) => t.replace(/^\[Handbook page \d+\]$/gm, " ").replace(/\s+/g, " ").trim();
  // Sentences of each that the other doesn't have: a few planted mistakes pass, a different handbook doesn't.
  const split = (t: string) => flat(t).split(/(?<=[.!?:])\s+/);
  const a = split(await res.text()), b = split(prompt.slice(start + 32, end));
  const changed = (x: string[], y: string[]) => { const have = new Set(y); return x.reduce((n, t) => n + (have.has(t) ? 0 : t.length), 0); };
  if (changed(a, b) > DEMO_EDIT || changed(b, a) > DEMO_EDIT) {
    return "Without a code, a sample handbook can have a few small edits and is checked against its own state. To check your own handbook, email hi@backpr.com for a free code.";
  }
  return "";
}

class BeamError extends Error {
  billed: boolean; // true when Beam may have done (and been paid for) the work
  constructor(message: string, billed: boolean) { super(message); this.billed = billed; }
}

async function beam(env: Env, prompt: string, effort: "low" | "high", est: number, retry = false) {
  // A retry samples (temperature 0.7): at temperature 0 Beam sometimes repeats a runaway answer that fills its budget.
  const body = JSON.stringify({ model: MODEL, messages: [{ role: "user", content: prompt }], reasoning_effort: effort,
    max_completion_tokens: MAX_OUT[effort], temperature: retry ? 0.7 : 0 });
  for (let attempt = 0; ; attempt++) {
    const t0 = Date.now();
    let res: Response;
    try {
      res = await fetch(ROUTER, { method: "POST", body, signal: AbortSignal.timeout(280_000),
        headers: { Authorization: `Bearer ${env.HF_TOKEN}`, "Content-Type": "application/json" } });
    } catch (err) {  // a timeout may still be billed: Beam may have done the work
      const timeout = (err as Error).name === "TimeoutError";
      throw new BeamError(timeout ? "The AI service took too long. Please try again in a few minutes." : "Couldn't reach the AI service. Please try again in a minute.", timeout);
    }
    if (res.ok) {
      let data: any;
      try { data = await res.json(); } catch { throw new BeamError("The AI service sent an answer that couldn't be read. Please try again.", true); }
      const choice = data.choices?.[0] || {}, usage = data.usage;
      const tokensIn = usage?.prompt_tokens || 0, tokensOut = usage?.completion_tokens || 0;
      const cost = usage ? +((tokensIn * PRICE_IN + tokensOut * PRICE_OUT) / 1e6).toFixed(6) : est;  // no usage: charge the estimate
      return { content: choice.message?.content || "", finish: choice.finish_reason || "", tokens_in: tokensIn, tokens_out: tokensOut,
        cost, seconds: (Date.now() - t0) / 1000 };
    }
    if ([401, 402, 403].includes(res.status)) throw new BeamError(PAUSED, false); // token or credit problem: nothing to retry
    if (attempt === 0 && [429, 500, 502, 503, 504].includes(res.status)) { await new Promise((r) => setTimeout(r, 5000)); continue; }
    throw new BeamError("The AI service didn't answer. Please try again in a minute; a failed try doesn't use up your check.", false);
  }
}

async function api(req: Request, env: Env, url: URL): Promise<Response> {
  if (env.RL) {
    const { success } = await env.RL.limit({ key: `${url.pathname}:${req.headers.get("CF-Connecting-IP") || "?"}` });
    if (!success) return json(req, { error: "Too many requests. Please wait a minute and try again." }, 429);
  }
  const budget = env.BUDGET.get(env.BUDGET.idFromName("global"));
  if (url.pathname === "/spent") {  // read-only: dollars spent on Beam through this site, and the caps, for monitoring
    if (req.method !== "GET") return json(req, { error: "Not found." }, 404);
    const cents = (n: number) => Math.round(n * 100) / 100, sp = await budget.spent();
    return json(req, { codes_today: cents(sp.codes_today), demo_today: cents(sp.demo_today), total: cents(sp.total),
      caps: { codes_day: Number(env.DAILY_USD || 1), demo_day: Number(env.DEMO_USD || 1), total: Number(env.TOTAL_USD || 3) } });
  }
  if (url.pathname === "/code") {
    if (req.method !== "GET") return json(req, { error: "Not found." }, 404);
    const code = (url.searchParams.get("code") || "").trim(), rule = ruleFor(env, code);
    if (!rule) return json(req, { valid: false, left_today: 0, max_states: 0 });
    return json(req, { valid: true, left_today: await budget.left(code, rule.per_day ?? 1), max_states: rule.max_states ?? 3,
      paused: env.LIVE_OFF === "1" });
  }
  if (req.method !== "POST") return json(req, { error: "Not found." }, 404);

  let input: { code?: string; check?: string; effort?: string; prompt?: string; retry?: boolean };
  try { input = await req.json(); } catch { return json(req, { error: "Bad request." }, 400); }
  const code = String(input.code || "").trim(), check = String(input.check || "").slice(0, 64);
  const effort: "low" | "high" = input.effort === "high" ? "high" : "low", prompt = String(input.prompt || "");
  if (prompt.length > MAX_PROMPT) return json(req, { error: "That handbook is too long to check. Try a shorter file, or the main policy pages only." }, 413);
  if (!check || !(await isInspection(prompt))) return json(req, { error: "This request doesn't look like a CareRules check. Please reload the page and try again." }, 400);
  const state = prompt.slice(13, 15);

  const cacheKey = `cache:${await sha256(effort + "\n" + prompt)}`;
  const hit = await env.KV.get(cacheKey, "json");
  if (hit) return json(req, { ...(hit as object), cost: 0, cached: true });

  if (env.LIVE_OFF === "1") return json(req, { error: PAUSED }, 503);
  let rule = ruleFor(env, code), key = code;
  if (!rule && code === "DEMO") {
    const problem = await demoProblem(env, req, prompt, effort);
    if (problem) return json(req, { error: problem }, 403);
    rule = demoRule(env);
    // per visitor, per day; the secret makes the stored value impossible to turn back into an address
    key = `DEMO-${(await sha256(`${env.HF_TOKEN}|${req.headers.get("CF-Connecting-IP") || "?"}|${day()}`)).slice(0, 16)}`;
  }
  if (!rule) return json(req, { error: "Live checks need an access code. Email hi@backpr.com for one; it's free." }, 403);
  // Reserve the worst case (every character a token, the whole output budget); settle refunds the difference.
  const est = +((prompt.length / 2.5) * PRICE_IN / 1e6 + MAX_OUT[effort] * PRICE_OUT / 1e6).toFixed(6);
  const v = await budget.reserve(key, check, state, rule, est, Number(env.DAILY_USD || 1), Number(env.TOTAL_USD || 3));
  if (!v.ok) {
    const msg = {
      code: rule.pool ? `That's today's sample checks from this connection. ${RESETS}` : `This code's check for today is used. ${RESETS}`,
      calls: "This check has reached its limit. Please start a new check tomorrow.",
      states: `This code covers ${rule.max_states ?? 3} state${(rule.max_states ?? 3) === 1 ? "" : "s"} per check.`,
      code_budget: `This code has reached today's limit. ${RESETS}`,
      budget: `Today's free checks are used up. ${RESETS} The sample reports still work.`,
      total: "Free checks are paused for now. The sample reports still work.",
    }[v.why!];
    return json(req, { error: msg }, 429);
  }

  let out: Awaited<ReturnType<typeof beam>> | null = null, failure: BeamError | null = null;
  try { out = await beam(env, prompt, effort, est, input.retry === true); } catch (err) { failure = err instanceof BeamError ? err : new BeamError("The check failed. Please try again.", false); }
  await budget.settle(key, check, rule, v.day, est, out ? out.cost : est, !out && !failure!.billed);
  if (!out) return json(req, { error: failure!.message }, 502);
  if (out.finish === "stop" && readable(out.content)) {
    try { await env.KV.put(cacheKey, JSON.stringify(out), { expirationTtl: 7 * 86400 }); } catch { /* the cache is optional */ }
  }
  return json(req, { ...out, cached: false });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (!["/code", "/beam", "/spent"].includes(url.pathname)) return env.ASSETS.fetch(req);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    try {
      return await api(req, env, url);
    } catch {
      return json(req, { error: "The checking service had a problem. Please try again in a minute." }, 503);
    }
  },
};
