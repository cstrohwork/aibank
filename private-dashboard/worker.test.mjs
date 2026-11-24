import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import worker, { authenticate } from './worker.mjs';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const now = 1800000000;
const env = { CF_ACCESS_AUD: 'test-audience', ADMIN_EMAIL: 'admin@example.invalid' };
const issuer = 'https://aibank-ai.cloudflareaccess.com';
const pair = await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const jwk = {...await crypto.subtle.exportKey('jwk',pair.publicKey),kid:'test-key',alg:'RS256',use:'sig'};
const enc = x=>Buffer.from(JSON.stringify(x)).toString('base64url');
const claims = {iss:issuer,aud:[env.CF_ACCESS_AUD],email:env.ADMIN_EMAIL,exp:now+60};
async function token(overrides={},header={}) {
 const data=enc({alg:'RS256',kid:'test-key',...header})+'.'+enc({...claims,...overrides});
 return data+'.'+Buffer.from(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,Buffer.from(data))).toString('base64url');
}
const keys=async (url,opts)=>{assert.equal(url,issuer+'/cdn-cgi/access/certs');assert.equal(opts.redirect,'error');return Response.json({keys:[jwk]});};
test('valid signed JWT',async()=>assert.equal(await authenticate(await token(),env,keys,now),true));
for(const [name,override] of Object.entries({issuer:{iss:'https://wrong.invalid'},audience:{aud:['wrong']},expired:{exp:now},future:{nbf:now+1},email:{email:'other@example.invalid'}})){
 test('reject '+name,async()=>assert.equal(await authenticate(await token(override),env,keys,now),false));
}
test('reject wrong algorithm and unknown key',async()=>{
 for(const h of [{alg:'none'},{kid:'unknown'},{crit:['x']}]) assert.equal(await authenticate(await token({},h),env,keys,now),false);
});
test('reject tampered payload and missing config',async()=>{
 const t=await token(); const [h,p,s]=t.split('.');
 assert.equal(await authenticate(h+'.'+enc({...claims,exp:now+999})+'.'+s,env,keys,now),false);
 assert.equal(await authenticate(t,{},keys,now),false);
 assert.equal(await authenticate(null,env,keys,now),false);
});
test('fail closed on certificate outage or duplicate key',async()=>{
 const t=await token();
 assert.equal(await authenticate(t,env,async()=>{throw Error('offline')},now),false);
 assert.equal(await authenticate(t,env,async()=>Response.json({keys:[jwk,jwk]}),now),false);
});
test('reject alternate host and unauthenticated requests',async()=>{
 assert.equal((await worker.fetch(new Request('https://alternate.invalid/'),env)).status,404);
 const r=await worker.fetch(new Request('https://dashboard.ainvestmentbank.ai/'),env);
 assert.equal(r.status,403);assert.equal(r.headers.get('Cache-Control'),'no-store');
});

test('pinned administrator digest accepts only matching signed identity',async()=>{
 const digest=Buffer.from(await crypto.subtle.digest('SHA-256',Buffer.from(env.ADMIN_EMAIL))).toString('hex');
 const pinned={CF_ACCESS_AUD:env.CF_ACCESS_AUD,ADMIN_EMAIL_SHA256:digest};
 assert.equal(await authenticate(await token(),pinned,keys,now),true);
 assert.equal(await authenticate(await token({email:'other@example.invalid'}),pinned,keys,now),false);
 assert.equal(await authenticate(await token(),{...pinned,ADMIN_EMAIL_SHA256:'0'.repeat(64)},keys,now),false);
});
