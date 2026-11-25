// Authenticated, read-only delivery dashboard. It reports public GitHub Actions
// execution state; no repository contents or private telemetry are exposed.
const issuer = "https://aibank-ai.cloudflareaccess.com";
const host = "dashboard.ainvestmentbank.ai";
const repository = "cstrohwork/aibank";
function decode(s) {
  if (!/^[A-Za-z0-9_-]+$/.test(s)) throw Error("encoding");
  return Uint8Array.from(atob(s.replace(/-/g,"+").replace(/_/g,"/")), c=>c.charCodeAt(0));
}
const parse = s=>JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(decode(s)));
export async function authenticate(token, env, fetcher=fetch, now=Math.floor(Date.now()/1000)) {
  if (!env.CF_ACCESS_AUD || (!env.ADMIN_EMAIL && !env.ADMIN_EMAIL_SHA256) || !token || token.length>16384) return false;
  try {
    const parts=token.split(".");
    if(parts.length!==3) return false;
    const [h,p,s]=parts, header=parse(h), claims=parse(p);
    if(header.alg!=="RS256" || typeof header.kid!=="string" || header.crit!==undefined) return false;
    if(claims.iss!==issuer || !Array.isArray(claims.aud) || !claims.aud.includes(env.CF_ACCESS_AUD)) return false;
    if(!Number.isFinite(claims.exp) || claims.exp<=now || (claims.nbf!==undefined && (!Number.isFinite(claims.nbf)||claims.nbf>now))) return false;
    if(typeof claims.email!=="string" || !claims.email) return false;
    if(env.ADMIN_EMAIL_SHA256) {
      const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(claims.email.toLowerCase()));
      if(Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("")!==env.ADMIN_EMAIL_SHA256) return false;
    } else if(claims.email.toLowerCase()!==env.ADMIN_EMAIL.toLowerCase()) return false;
    const res=await fetcher(issuer+"/cdn-cgi/access/certs",{redirect:"error"});
    if(!res.ok) return false;
    const {keys}=await res.json();
    const matches=keys.filter(k=>k.kid===header.kid && k.kty==="RSA" && (!k.alg||k.alg==="RS256") && (!k.use||k.use==="sig"));
    if(matches.length!==1) return false;
    const key=await crypto.subtle.importKey("jwk",matches[0],{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]);
    return await crypto.subtle.verify("RSASSA-PKCS1-v1_5",key,decode(s),new TextEncoder().encode(h+"."+p));
  } catch {return false;}
}
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const date = value => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "—" : parsed.toISOString().replace("T"," ").replace(/\.\d{3}Z$/," UTC");
};
const badge = run => run.status === "in_progress" || run.status === "queued"
  ? "running" : run.conclusion || run.status || "unknown";
function render(runs, degraded=false) {
  const active = runs.filter(run => run.status === "in_progress" || run.status === "queued").length;
  const failed = runs.filter(run => run.conclusion === "failure").length;
  const latest = runs[0];
  const rows = runs.length ? runs.map(run => {
    const state = badge(run);
    return `<tr><td>${esc(run.name)}</td><td><span class="badge ${esc(state)}">${esc(state.replaceAll("_"," "))}</span></td><td>${esc(run.event)}</td><td>${esc(date(run.run_started_at || run.created_at))}</td><td>${esc(date(run.updated_at))}</td><td><a href="${esc(run.html_url)}" target="_blank" rel="noopener noreferrer">Run details ↗</a></td></tr>`;
  }).join("") : '<tr><td colspan="6">No workflow runs were returned.</td></tr>';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capital Signal Dashboard</title><style>
:root{color-scheme:dark;--bg:#081321;--panel:#0e1d2e;--line:#20364d;--text:#e7eef6;--muted:#9bb0c5;--blue:#76b7ff}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(140deg,#0b1c30,#07111e 55%);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:34px 22px 60px}.brand{color:#9db7d2;font-size:12px;font-weight:700;letter-spacing:.17em;text-transform:uppercase}
h1{font-size:clamp(27px,4vw,40px);letter-spacing:-.03em;margin:8px 0 3px}.sub{color:var(--muted);margin:0 0 24px}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:24px 0}
.card,.section{background:#0e1d2eea;border:1px solid var(--line);border-radius:13px}.card{padding:17px 19px}.label{font-size:12px;color:var(--muted)}.value{font-size:27px;font-weight:700;margin-top:3px}
.section{overflow:hidden}.sectionhead{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:12px}
h2{font-size:17px;margin:0}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.notice{padding:11px 20px;background:#142b41;color:#bdd7f1;border-bottom:1px solid var(--line)}.warn{background:#3a2d14;color:#f3d68c}
.wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:760px;text-align:left}th,td{padding:12px 15px;border-bottom:1px solid #1a3045}th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:650}td{font-size:13px}tr:last-child td{border:0}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;background:#29394c;color:#c9d6e3;font-size:11px;font-weight:700;text-transform:capitalize}
.badge.success{background:#123a31;color:#7fe0bd}.badge.failure{background:#48242c;color:#ff9da9}.badge.running,.badge.queued{background:#173454;color:#9acbff}
.links{display:flex;gap:17px;flex-wrap:wrap;margin:17px 2px;color:var(--muted);font-size:13px}.foot{color:var(--muted);font-size:12px;margin-top:18px}
@media(max-width:640px){main{padding:25px 14px}.cards{gap:8px}.card{padding:13px 12px}.value{font-size:23px}.sectionhead{align-items:flex-start;flex-direction:column}}
</style></head><body><main><div class="brand">AIBank · Capital Signal Intelligence</div><h1>Delivery Dashboard</h1><p class="sub">Authenticated view of recent automation and publication activity.</p>
<div class="cards"><div class="card"><div class="label">Recent workflow runs</div><div class="value">${runs.length}</div></div><div class="card"><div class="label">Active now</div><div class="value">${active}</div></div><div class="card"><div class="label">Failures in latest 30 runs</div><div class="value">${failed}</div></div></div>
<section class="section"><div class="sectionhead"><h2>Latest GitHub Actions runs</h2><a href="https://github.com/${repository}/actions" target="_blank" rel="noopener noreferrer">Open all workflows ↗</a></div>${degraded?'<div class="notice warn">Live workflow data is temporarily unavailable. Retry in a moment.</div>':'<div class="notice">Read-only feed from the public repository. Status is refreshed when this page loads.</div>'}<div class="wrap"><table><thead><tr><th>Workflow</th><th>Status</th><th>Trigger</th><th>Started</th><th>Updated</th><th>Details</th></tr></thead><tbody>${rows}</tbody></table></div></section>
<div class="links"><a href="https://ainvestmentbank.ai/CapitalSignal/">Capital Signal site ↗</a><a href="https://ainvestmentbank.ai/CapitalSignal/workerdashboard/">Public delivery status ↗</a><a href="https://github.com/${repository}">Source repository ↗</a></div>
<div class="foot">Private access is enforced by Cloudflare Access. The feed contains public GitHub Actions metadata and does not include worker secrets, restart controls, or private telemetry.</div></main></body></html>`;
}
export default {async fetch(request,env) {
  const url=new URL(request.url);
  const headers={"Cache-Control":"no-store","Content-Type":"text/html; charset=utf-8","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'","Referrer-Policy":"no-referrer"};
  const reply=(body,status,type=headers["Content-Type"])=>new Response(body,{status,headers:{...headers,"Content-Type":type}});
  if(url.hostname!==host || url.protocol!=="https:") return reply("Not found",404,"text/plain; charset=utf-8");
  if(!await authenticate(request.headers.get("Cf-Access-Jwt-Assertion"),env)) return reply("Forbidden",403,"text/plain; charset=utf-8");
  if(request.method!=="GET") return reply("Method not allowed",405,"text/plain; charset=utf-8");
  if(url.pathname!=="/" || url.search) return reply("Not found",404,"text/plain; charset=utf-8");
  let runs=[], degraded=false;
  try {
    const response=await fetch(`https://api.github.com/repos/${repository}/actions/runs?per_page=30`,{
      headers:{"Accept":"application/vnd.github+json","User-Agent":"CapitalSignal-Delivery-Dashboard"}
    });
    if(!response.ok) throw Error("GitHub API unavailable");
    const data=await response.json();
    if(!Array.isArray(data.workflow_runs)) throw Error("Unexpected workflow response");
    runs=data.workflow_runs;
  } catch { degraded=true; }
  return reply(render(runs,degraded),200);
}};
