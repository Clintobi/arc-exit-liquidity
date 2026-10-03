// Arc Token Check: reads ArcFlagRegistry and the token itself straight from Arc mainnet.

const RPC = "https://rpc.mainnet.arc.io";
const REGISTRY = "0x27B0AA7E1824d4561c02363bf1c3Ac47e4548221";
const USDC = "0x3600000000000000000000000000000000000000";
const EXPLORER = "https://explorer.arc.io/address/";

const SEL = {
  record: "0x617fba04", // getRecord(address)
  count: "0x5d214e01",  // flaggedCount()
  name: "0x06fdde03",
  symbol: "0x95d89b41",
};

const FLAG = { COLLISION: 1, HIGH_FEE: 2, SOLO: 4, NEVER: 8, DYNAMIC: 16 };

const $ = (id) => document.getElementById(id);
const form = $("form");
const input = $("addr");
const msg = $("addr-msg");
const result = $("result");
const go = $("go");

let meta = null; // findings.json: block the records hold through, and its date

// ---------------------------------------------------------------- chain I/O

async function rpc(method, params, timeout = 12000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(RPC, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: ctl.signal,
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error.message || "RPC error");
    return j.result;
  } finally {
    clearTimeout(t);
  }
}

const ethCall = (to, data) => rpc("eth_call", [{ to, data }, "latest"]);
const pad = (a) => a.toLowerCase().replace(/^0x/, "").padStart(64, "0");
const words = (h) => h.slice(2).match(/.{64}/g) || [];

function decodeString(hex) {
  if (!hex || hex === "0x") return null;
  const h = hex.slice(2);
  try {
    let bytes;
    if (h.length >= 192) {
      const len = parseInt(h.slice(64, 128), 16);
      if (!len || len > 200) return null;
      bytes = h.slice(128, 128 + len * 2);
    } else {
      bytes = h.slice(0, 64).replace(/(00)+$/, "");
    }
    const arr = new Uint8Array(bytes.match(/.{2}/g)?.map((b) => parseInt(b, 16)) || []);
    const s = new TextDecoder().decode(arr).replace(/[\u0000-\u001f]/g, "").trim();
    return s || null;
  } catch {
    return null;
  }
}

async function readToken(addr) {
  const [name, symbol] = await Promise.all([
    ethCall(addr, SEL.name).then(decodeString).catch(() => null),
    ethCall(addr, SEL.symbol).then(decodeString).catch(() => null),
  ]);
  return { name, symbol };
}

async function readRecord(addr) {
  const w = words(await ethCall(REGISTRY, SEL.record + pad(addr)));
  const n = (i) => Number(BigInt("0x" + (w[i] || "0")));
  return { flags: n(0), pools: n(1), wallets: n(2), maxFee: n(3), blockSeen: n(4), epoch: n(5) };
}

// ---------------------------------------------------------------- formatting

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n).toLocaleString("en-US");
const short = (a) => a.slice(0, 6) + "…" + a.slice(-4);
const pct = (fee) => {
  const p = fee / 1e4; // hundredths of a bip
  return (p >= 10 ? Math.round(p) : p.toFixed(2).replace(/\.?0+$/, "")) + "%";
};
const dateOf = (ts) => new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
function asOf(block) {
  const b = block || meta?.blockSeen;
  if (meta?.blockSeen === b && meta?.blockSeenTime) return `${dateOf(meta.blockSeenTime)}<small>block ${fmt(b)}</small>`;
  return `block ${fmt(b)}`;
}
function heldThrough(block) {
  const b = block || meta?.blockSeen;
  if (!b) return "";
  return meta?.blockSeen === b && meta?.blockSeenTime ? `block ${fmt(b)} (${dateOf(meta.blockSeenTime)})` : `block ${fmt(b)}`;
}

const ICON = {
  flag: '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 2.8 19.5h18.4L12 3.5Z"/><path d="M12 10v4.5"/><circle cx="12" cy="17" r=".6" fill="currentColor"/></svg>',
  real: '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12.2 2.7 2.7L16.2 9.4"/></svg>',
  none: '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>',
  info: '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/></svg>',
  dot: '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>',
};

// ---------------------------------------------------------------- rendering

function identity(addr, tok) {
  const label = tok === "wallet"
    ? `<span class="tok">Wallet or empty address</span>`
    : tok?.symbol
    ? `<span class="tok">${esc(tok.symbol)}</span>${tok.name && tok.name !== tok.symbol ? ` <span>${esc(tok.name)}</span>` : ""}`
    : `<span class="tok">Unnamed contract</span>`;
  return `<div class="identity">${label}<span class="addr">${esc(addr)}</span></div>`;
}

function actions(addr) {
  return `<div class="actions">
    <a href="${EXPLORER}${addr}" target="_blank" rel="noopener">View on Arc explorer</a>
    <button class="linkbtn" type="button" data-copy="link">Copy link to this result</button>
    <button class="linkbtn" type="button" data-copy="call" data-addr="${addr}">Copy the contract call</button>
  </div>`;
}

function realUsdc() {
  return `<div class="callout">
    <p><strong>Arc's real USDC</strong> is <code class="full">${USDC}</code></p>
    <div class="callout-actions">
      <button class="btn-quiet" type="button" data-copy="usdc">Copy real USDC address</button>
      <a class="btn-quiet" href="./?a=${USDC}">Check it</a>
    </div>
  </div>`;
}

function sheet({ tone, mark, icon, verdict, sub, addr, tok, body = "" }) {
  return `<article class="sheet" data-tone="${tone}">
    <header class="sheet-head">
      <span class="mark">${ICON[icon]}${esc(mark)}</span>
      <h2 class="verdict">${verdict}</h2>
      ${sub ? `<p class="verdict-sub">${sub}</p>` : ""}
      ${addr ? identity(addr, tok) : ""}
    </header>
    ${body ? `<div class="sheet-body">${body}</div>` : ""}
  </article>`;
}

function limits(block) {
  return `<details class="limits">
    <summary>What this does and doesn't cover</summary>
    <p>The registry records two facts today: contracts using the USDC name at an address that isn't Arc's USDC, and pools whose realised fee reached 50% or more. Records hold through ${heldThrough(block)}. Pools and trades after that aren't in yet.</p>
    <p>It doesn't read the contract's code, rate the people behind a token, or predict its price. Flags are published by one address for now, and clearing a wrong flag costs the same as setting one. To report a mistake, <a href="https://github.com/Clintobi/arc-exit-liquidity/issues" target="_blank" rel="noopener">open an issue</a>.</p>
  </details>`;
}

function renderFlagged(addr, tok, rec) {
  const hits = [];
  const sym = tok.symbol || "USDC";
  if (rec.flags & FLAG.COLLISION) {
    hits.push({
      title: `Uses the name ${esc(sym)} at an address that isn't Arc's USDC`,
      text: `Arc's USDC lives at <code>0x3600…0000</code> and is the same balance you pay gas with. Swapping into this contract gets you this token, not dollars.`,
    });
  }
  if (rec.flags & FLAG.HIGH_FEE) {
    hits.push({
      title: `A pool holding it kept ${pct(rec.maxFee)} of a trade`,
      text: `That's the fee actually taken on real swaps, not just the pool's setting. At that rate, buying and selling back loses most of what you put in.`,
    });
  }
  if (rec.flags & FLAG.SOLO) hits.push({ title: "Only one wallet has ever traded it", text: "Every swap on record came from a single sender." });
  if (rec.flags & FLAG.NEVER) hits.push({ title: "It has a pool, but no trade has settled", text: "A price may show, but nobody has actually bought or sold." });
  if (rec.flags & FLAG.DYNAMIC) hits.push({ title: "A hook sets its fee on every trade", text: "No fixed rate can be quoted ahead of time." });

  let verdict = "This token is flagged";
  if (rec.flags & FLAG.COLLISION) verdict = `Calls itself ${esc(sym)}, but it isn't Arc's USDC`;
  else if (rec.flags & FLAG.HIGH_FEE) verdict = `Its pool kept ${pct(rec.maxFee)} of a trade`;

  // One finding: its explanation becomes the sub-line instead of repeating the verdict below.
  const single = hits.length === 1;
  const body = `
    ${rec.flags & FLAG.COLLISION ? realUsdc() : ""}
    ${single ? "" : `<ul class="findings">${hits.map((h) => `<li><span class="ico">${ICON.dot}</span><div><strong>${h.title}</strong><p>${h.text}</p></div></li>`).join("")}</ul>`}
    <dl class="evidence">
      <div><dt>Pools it trades in</dt><dd>${fmt(rec.pools)}</dd></div>
      <div><dt>Wallets that traded it</dt><dd>${fmt(rec.wallets)}</dd></div>
      <div><dt>Highest fee taken</dt><dd>${pct(rec.maxFee)}</dd></div>
      <div><dt>Record current to</dt><dd>${asOf(rec.blockSeen)}</dd></div>
    </dl>
    <p class="fine">These are facts from Arc's chain history, not a judgement of the people behind the token.</p>
    ${actions(addr)}
    ${limits(rec.blockSeen)}`;

  return sheet({
    tone: "flag", icon: "flag",
    mark: single ? "Flagged" : `Flagged · ${hits.length} findings`,
    verdict, sub: single ? hits[0].text : "", addr, tok, body,
  });
}

function renderClear(addr, tok) {
  const body = `${actions(addr)}${limits()}`;
  return sheet({
    tone: "none", icon: "none", mark: "Not flagged",
    verdict: "Neither problem was found",
    sub: `As of ${heldThrough()}, it doesn't use the USDC name at another address, and none of its pools took 50% or more of a trade. Not flagged doesn't mean safe: these are the only two things checked.`,
    addr, tok, body,
  });
}

function renderTooNew(addr, tok) {
  const body = `${actions(addr)}${limits()}`;
  return sheet({
    tone: "info", icon: "info", mark: "Too new to check",
    verdict: "This token is newer than the record",
    sub: `It didn't exist yet at ${heldThrough()}, when the record was last published, so it hasn't been checked at all. Treat it as unknown, not as clean.`,
    addr, tok, body,
  });
}

function renderUsdc(addr) {
  return sheet({
    tone: "real", icon: "real", mark: "Genuine",
    verdict: "This is Arc's USDC",
    sub: "The official USDC contract. It's the same balance you pay gas with: 6 decimals when you hold it as a token, 18 when it pays for gas.",
    addr, tok: { symbol: "USDC", name: "USD Coin" },
    body: actions(addr),
  });
}

function renderNotContract(addr) {
  return sheet({
    tone: "info", icon: "info", mark: "Not a token",
    verdict: "This address isn't a contract",
    sub: "It's a wallet or an empty address, so there's no token to check. Copy the token's contract address, not a person's wallet or a pool.",
    addr, tok: "wallet",
    body: `<div class="actions"><a href="${EXPLORER}${addr}" target="_blank" rel="noopener">View on Arc explorer</a></div>`,
  });
}

function renderDown(addr, err) {
  return sheet({
    tone: "info", icon: "info", mark: "No answer",
    verdict: "Couldn't reach Arc",
    sub: `The public Arc RPC didn't respond${err ? ` (${esc(String(err).slice(0, 80))})` : ""}. Nothing is wrong with the address.`,
    addr: null,
    body: `<div class="actions"><button class="linkbtn" type="button" data-retry="${addr}">Try again</button></div>`,
  });
}

const skeleton = `<div class="sheet" aria-busy="true"><div class="skel"><i></i><i></i><i></i></div><span class="visually-hidden">Reading Arc mainnet…</span></div>`;

// ---------------------------------------------------------------- flow

function setError(text) {
  runId++; // drop any check still in flight
  result.innerHTML = "";
  document.body.classList.remove("has-result");
  go.disabled = false;
  msg.textContent = text;
  msg.classList.add("is-error");
  input.setAttribute("aria-invalid", "true");
}
function clearError() {
  msg.textContent = "42 characters, starting with 0x.";
  msg.classList.remove("is-error");
  input.removeAttribute("aria-invalid");
}

let runId = 0;
async function check(raw) {
  const addr = (raw || "").trim();
  if (!addr) { setError("Paste a token's contract address first."); input.focus(); return; }
  if (!/^0x[a-fA-F0-9]{40}$/.test(addr)) {
    setError(addr.length !== 42 ? `That's ${addr.length} characters. An address is 42, starting with 0x.` : "That isn't a valid address. Only 0–9 and a–f after the 0x.");
    input.focus();
    return;
  }
  clearError();
  input.scrollLeft = 0;

  const id = ++runId;
  const url = new URL(location.href);
  url.searchParams.set("a", addr);
  history.replaceState(null, "", url);

  go.disabled = true;
  result.innerHTML = skeleton;

  try {
    if (addr.toLowerCase() === USDC) { done(id, renderUsdc(addr)); return; }
    const code = await rpc("eth_getCode", [addr, "latest"]);
    if (!code || code === "0x") { done(id, renderNotContract(addr)); return; }
    const [rec, tok] = await Promise.all([readRecord(addr), readToken(addr)]);
    if (rec.flags) { done(id, renderFlagged(addr, tok, rec)); return; }
    // Not flagged: did the contract even exist when the record was published?
    let tooNew = false;
    if (meta?.blockSeen) {
      const then = await rpc("eth_getCode", [addr, "0x" + meta.blockSeen.toString(16)]).catch(() => null);
      tooNew = then === "0x";
    }
    done(id, tooNew ? renderTooNew(addr, tok) : renderClear(addr, tok));
  } catch (e) {
    done(id, renderDown(addr, e.name === "AbortError" ? "timed out" : e.message));
  }
}

function done(id, html) {
  if (id !== runId) return; // a newer check started
  result.innerHTML = html;
  go.disabled = false;
  document.body.classList.add("has-result");

  const verdict = result.querySelector(".verdict");
  const mark = result.querySelector(".mark")?.textContent.trim();
  // Announce only the verdict, not the whole sheet.
  $("announce").textContent = "";
  requestAnimationFrame(() => { $("announce").textContent = `${mark}. ${verdict?.textContent.trim() || ""}`; });

  if (verdict) {
    verdict.setAttribute("tabindex", "-1");
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    result.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
    verdict.focus({ preventScroll: true });
  }
}

// ---------------------------------------------------------------- wiring

form.addEventListener("submit", (e) => { e.preventDefault(); check(input.value); });
input.addEventListener("input", () => { if (input.getAttribute("aria-invalid")) clearError(); });
input.addEventListener("paste", () => setTimeout(() => {
  if (/^\s*0x[a-fA-F0-9]{40}\s*$/.test(input.value)) check(input.value);
}, 0));

const pasteBtn = $("paste");
if (navigator.clipboard?.readText) {
  pasteBtn.hidden = false;
  pasteBtn.addEventListener("click", async () => {
    try {
      const t = (await navigator.clipboard.readText()).trim();
      input.value = t;
      check(t);
    } catch {
      input.focus();
      toast("Press and hold the field to paste");
    }
  });
}

document.addEventListener("click", async (e) => {
  const chip = e.target.closest(".chip[data-a]");
  if (chip) { input.value = chip.dataset.a; check(chip.dataset.a); return; }
  const retry = e.target.closest("[data-retry]");
  if (retry) { check(retry.dataset.retry); return; }
  const copy = e.target.closest("[data-copy]");
  if (copy) {
    if (copy.dataset.copy === "usdc") {
      try { await navigator.clipboard.writeText(USDC); toast("Real USDC address copied"); }
      catch { toast("Couldn't copy. Select it manually."); }
      return;
    }
    const text = copy.dataset.copy === "link"
      ? location.href
      : `cast call ${REGISTRY} "getRecord(address)((uint8,uint32,uint32,uint32,uint64,uint32))" ${copy.dataset.addr} --rpc-url ${RPC}`;
    try { await navigator.clipboard.writeText(text); toast(copy.dataset.copy === "link" ? "Link copied" : "Contract call copied"); }
    catch { toast("Couldn't copy. Select it manually."); }
  }
});

let toastTimer;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

// ---------------------------------------------------------------- boot

async function boot() {
  const statusEl = $("status");
  const text = $("status-text");
  try {
    meta = await fetch("data/findings.json").then((r) => r.json());
    const fee = meta.tokens.find((t) => t.flags & FLAG.HIGH_FEE);
    if (fee) { const b = $("try-fee"); b.dataset.a = fee.address; b.hidden = false; }
  } catch { /* the page still works from chain reads alone */ }

  try {
    const count = Number(BigInt(await ethCall(REGISTRY, SEL.count)));
    text.textContent = `Registry live on Arc mainnet · ${fmt(count)} tokens on record` + (meta ? ` · records hold through ${heldThrough()}` : "");
  } catch {
    statusEl.classList.add("is-down");
    text.textContent = "Can't reach Arc right now. Checks will retry when you press Check.";
  }

  const a = new URL(location.href).searchParams.get("a");
  if (a) { input.value = a; check(a); }
}

boot();
