// Read-only authentication gate; no telemetry or restart access until reviewed.
const issuer = "https://aibank-ai.cloudflareaccess.com";
const host = "dashboard.ainvestmentbank.ai";
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
export default {async fetch(request,env) {
  const url=new URL(request.url);
  const headers={"Cache-Control":"no-store","Content-Type":"text/plain; charset=utf-8","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'","Referrer-Policy":"no-referrer"};
  const reply=(body,status)=>new Response(body,{status,headers});
  if(url.hostname!==host || url.protocol!=="https:") return reply("Not found",404);
  if(!await authenticate(request.headers.get("Cf-Access-Jwt-Assertion"),env)) return reply("Forbidden",403);
  if(request.method!=="GET") return reply("Method not allowed",405);
  if(url.pathname!=="/" || url.search) return reply("Not found",404);
  return reply("Capital Signal private dashboard: authentication verified. Telemetry integration pending.",200);
}};
