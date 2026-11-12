(function(root){'use strict';
function project(baseline,assumptions,scenario){
const required=['growth','margin','epsGrowth','pe','ev','growthSpread','marginSpread'];
if(required.some(k=>!Number.isFinite(assumptions[k])))throw Error('Complete all required assumptions.');
const a=assumptions;
if(a.growth>100||a.epsGrowth>100||Math.abs(a.margin)>1000||a.pe>200||a.ev>100||a.growthSpread>50||a.marginSpread>50||(a.fcfMargin!==null&&(!Number.isFinite(a.fcfMargin)||Math.abs(a.fcfMargin)>1000)))throw Error('Use growth up to 100%, margins within ±1,000%, P/E up to 200×, EV/revenue up to 100×, and adjustments up to 50 points.');
const shift=scenario==='bull'?1:scenario==='bear'?-1:0,g=a.growth+shift*a.growthSpread,m=a.margin+shift*a.marginSpread,eg=a.epsGrowth+shift*a.growthSpread;
if(g<=-100||eg<=-100||a.pe<=0||a.ev<=0||a.growthSpread<0||a.marginSpread<0)throw Error('Growth must exceed −100%; multiples must be positive and adjustments nonnegative.');
const f=baseline.facts,rev=f.revenue.val,eps=f.eps_diluted?.val,fcfm=Number.isFinite(a.fcfMargin)?a.fcfMargin+shift*a.marginSpread:null;
if(!Number.isFinite(rev)||rev<=0)throw Error('A positive finite reported revenue baseline is required.');
const rows=Array.from({length:5},(_,i)=>{let n=i+1,revenue=rev*Math.pow(1+g/100,n),earnings=Number.isFinite(eps)?eps*Math.pow(1+eg/100,n):null;return {year:Number(baseline.end.slice(0,4))+n,revenue,netMargin:m/100,netIncome:revenue*m/100,eps:earnings,fcf:fcfm===null?null:revenue*fcfm/100,impliedShareValue:earnings>0?earnings*a.pe:null,enterpriseValue:revenue*a.ev}});
if(rows.some(r=>Object.values(r).some(v=>v!==null&&!Number.isFinite(v))))throw Error('Scenario exceeds the supported numeric range.');
return rows;
}
const api={project};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ModelCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
