// Findings page: renders check/data/findings.json (built from the on-chain registry).

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString("en-US");
const usd = (n) => "$" + (n >= 1e9 ? (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B" : n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : Math.round(n));
const short = (a) => a.slice(0, 6) + "…" + a.slice(-4);
const pct = (fee) => { const p = fee / 1e4; return (p >= 10 ? Math.round(p) : p.toFixed(2).replace(/\.?0+$/, "")) + "%"; };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dateOf = (ts) => new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function row(t, cols) {
  const sym = t.symbol ? esc(t.symbol) : "<span class=\"mono\">no symbol</span>";
  return `<tr>
    <td><a href="./?a=${t.address}">${sym}</a></td>
    <td><span class="mono">${short(t.address)}</span></td>
    ${cols.map((c) => `<td class="r">${c}</td>`).join("")}
  </tr>`;
}

async function boot() {
  let d;
  try {
    d = await fetch("data/findings.json").then((r) => r.json());
  } catch {
    $("usdc-rows").innerHTML = $("fee-rows").innerHTML = `<tr><td colspan="5">Couldn't load the records. Refresh to try again.</td></tr>`;
    return;
  }
  const c = d.chain;
  const when = d.blockSeenTime ? dateOf(d.blockSeenTime) : `block ${fmt(d.blockSeen)}`;

  $("lede").textContent = `We indexed every Uniswap V4 swap on Arc straight from its public RPC: ${fmt(c.swaps)} swaps across ${fmt(c.poolsCreated)} pools, with no paid indexer in between. Two things a buyer should know before trading stood out. Both are now recorded on-chain, ${fmt(d.count)} tokens in all, current to ${when}.`;

  const imp = d.tokens.filter((t) => t.flags & 1);
  const impVol = imp.reduce((s, t) => s + t.volume, 0);
  $("usdc-p").textContent = `On Arc, USDC pays for gas and lives at one address, 0x3600…0000. ${fmt(imp.length)} other contracts call themselves USDC and still trade, with ${usd(impVol)} of volume between them. The two busiest are among the most traded tokens on the chain.`;
  $("usdc-rows").innerHTML = imp.slice(0, 10).map((t) => row(t, [usd(t.volume), fmt(t.wallets), fmt(t.pools)])).join("");
  $("usdc-more").innerHTML = imp.length > 10
    ? `Showing the 10 busiest of ${fmt(imp.length)}. Every one can be checked on the <a href="./">Check page</a> or read from the registry.`
    : "";

  const fee = d.tokens.filter((t) => t.flags & 2).sort((a, b) => b.maxFee - a.maxFee);
  $("fee-rows").innerHTML = fee.length
    ? fee.map((t) => row(t, [pct(t.maxFee), fmt(t.wallets), fmt(t.pools)])).join("")
    : `<tr><td colspan="5">None on record.</td></tr>`;

  // Context: DEX trading vs USDC moved
  const share = c.dexUsdcNet / c.usdcTransferredWeek1;
  $("ctx-fig").hidden = false;
  $("ctx-fill").style.width = Math.max(share * 100, 0.6) + "%";
  $("ctx-bar").setAttribute("aria-label", `DEX trading was about ${(share * 100).toFixed(1)}% of USDC transferred in week one`);
  $("ctx-left").textContent = `DEX trading ${usd(c.dexUsdcNet)}`;
  $("ctx-right").textContent = `USDC transferred, week one ${usd(c.usdcTransferredWeek1)}`;
  $("ctx-p").textContent = `Launch-week coverage called Arc a memecoin casino. In its first week Circle reported ${usd(c.usdcTransferredWeek1)} of USDC transferred; the trading we indexed comes to about ${usd(c.dexUsdcNet)}, under ${Math.ceil(share * 100)}% of it.`;
  $("ctx-list").innerHTML = [
    `${fmt(c.poolsCreated)} pools created, ${fmt(c.poolsTraded)} ever traded, ${fmt(c.pools100Wallets)} reached 100 different wallets.`,
    `${fmt(c.soloPools)} pools were only ever traded by one wallet. That's in the index but not yet published to the registry.`,
    `The two figures measure different things (all USDC transfers vs swap volume), so read the ratio as direction, not precision.`,
  ].map((s) => `<li>${s}</li>`).join("");

  // Which flag bits are actually published
  const counts = {};
  for (const t of d.tokens) for (const b of [1, 2, 4, 8, 16]) if (t.flags & b) counts[b] = (counts[b] || 0) + 1;
  document.querySelectorAll("#flag-rows [data-bit]").forEach((td) => {
    const n = counts[td.dataset.bit] || 0;
    td.textContent = n ? fmt(n) : "not yet";
  });
  $("limit-block").textContent = `Every record holds through block ${fmt(d.blockSeen)} (${when}). Newer pools aren't in until the next publishing round.`;
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy-text]");
  if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.copyText); toast("Address copied"); }
  catch { toast("Couldn't copy. Select it manually."); }
});

let timer;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(timer);
  timer = setTimeout(() => el.classList.remove("show"), 1800);
}

boot();
