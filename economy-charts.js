/* България в числа — статистически визуализации от проверени серии в economy.json */
(async function () {
 "use strict";
 const nf = new Intl.NumberFormat("bg-BG",{maximumFractionDigits:1});
 const n0 = new Intl.NumberFormat("bg-BG",{maximumFractionDigits:0});
 const $ = id => document.getElementById(id);
 const palette = {blue:"#315f91",green:"#24765f",red:"#b64b45",ochre:"#a8732e",muted:"#66778b"};
 function node(tag, text, parent, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(parent)parent.appendChild(e); if(cls)e.className=cls; return e; }
 function series(data,id){return (data.series||[]).find(s=>s.id===id);}
 function valid(s){return s&&(s.points||[]).filter(p=>Number.isFinite(p.value)&&Number.isInteger(p.year)).sort((a,b)=>a.year-b.year);}
 function latest(s){const p=valid(s);return p.length?p[p.length-1]:null;}
 function kpi(hostId, s, suffix, label){const p=latest(s);if(!p)return;const box=node("div",undefined,$(hostId),"c");node("div",n0.format(p.value)+(suffix||""),box,"n");node("div",label||s.title,box,"l");node("div",String(p.year)+" · Евростат",box,"s");}
 function chart(hostId,s,color,unit){const host=$(hostId);if(!host||!s)return;const points=valid(s);if(points.length<2){node("p","Недостатъчно налични наблюдения.",host,"news-empty");return;}
 const W=720,H=250,L=62,R=18,T=18,B=38, vals=points.map(p=>p.value),lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo||Math.abs(hi)||1)*.14,min=lo-pad,max=hi+pad;
 const x=i=>L+i*(W-L-R)/(points.length-1), y=v=>T+(max-v)*(H-T-B)/(max-min);
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.setAttribute("role","img");svg.setAttribute("aria-label",s.title);host.appendChild(svg);
 function el(tag,attrs,txt){const e=document.createElementNS(svg.namespaceURI,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(txt!==undefined)e.textContent=txt;svg.appendChild(e);return e;}
 for(let i=0;i<=4;i++){const v=min+(max-min)*i/4;el("line",{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:"#d5dee8"});el("text",{x:L-8,y:y(v)+4,"text-anchor":"end"},nf.format(v));}
 const d=points.map((p,i)=>(i?"L":"M")+x(i)+" "+y(p.value)).join(" ");el("path",{d,fill:"none",stroke:color||palette.blue,"stroke-width":3,"stroke-linecap":"round","stroke-linejoin":"round"});
 const step=Math.max(1,Math.ceil(points.length/8));points.forEach((p,i)=>{const c=el("circle",{cx:x(i),cy:y(p.value),r:3.5,fill:color||palette.blue});const title=document.createElementNS(svg.namespaceURI,"title");title.textContent=p.year+": "+nf.format(p.value)+(unit||"");c.appendChild(title);if(i%step===0||i===points.length-1)el("text",{x:x(i),y:H-12,"text-anchor":"middle"},String(p.year));});
 const details=node("details",undefined,host);node("summary","Таблица с точните годишни стойности",details);const wrap=node("div",undefined,details,"tw"),table=node("table",undefined,wrap),thead=node("thead",undefined,table),tr=node("tr",undefined,thead);["Година","Стойност","Бележка"].forEach(t=>node("th",t,tr));const tb=node("tbody",undefined,table);points.forEach(p=>{const r=node("tr",undefined,tb);node("td",String(p.year),r);node("td",nf.format(p.value)+(unit||""),r);node("td",p.flag||"—",r);});
 }
 try{
 const res=await fetch("economy.json",{cache:"no-store"});if(!res.ok)throw Error("HTTP "+res.status);const data=await res.json();
 const defs=[
 ["gdp_real_growth","eco-gdp-chart",palette.blue,"%"],
 ["gdp_per_capita_current_eur","eco-gdpcap-chart",palette.green," €"],
 ["employment_rate_20_64","lab-employment-chart",palette.green,"%"],
 ["unemployment_rate_15_74","lab-unemployment-chart",palette.red,"%"],
 ["gdp_pps_index","eu-ppp-chart",palette.ochre,""],
 ["population_total","demo-population-chart",palette.blue,""]
 ];
 defs.forEach(([id,target,color,unit])=>chart(target,series(data,id),color,unit));
 kpi("eco-kpis",series(data,"gdp_real_growth"),"%","Реален растеж на БВП");
 kpi("lab-kpis",series(data,"employment_rate_20_64"),"%","Заетост, 20–64 г.");
 kpi("lab-kpis",series(data,"unemployment_rate_15_74"),"%","Безработица, 15–74 г.");
 kpi("eu-kpis",series(data,"gdp_pps_index"),"","БВП на човек, ЕС = 100");
 kpi("demo-kpis",series(data,"population_total"),"","Население към 1 януари");
 kpi("trade-kpis",series(data,"exports_goods_mio_eur")," млн. €","Износ на стоки");
 kpi("trade-kpis",series(data,"imports_goods_mio_eur")," млн. €","Внос на стоки");
 const exp=series(data,"exports_goods_mio_eur"),imp=series(data,"imports_goods_mio_eur");
 if(exp&&imp){const host=$("trade-chart");const e=latest(exp),i=latest(imp);if(host&&e&&i)node("p","Последни налични стойности: износ "+nf.format(e.value)+" млн. евро; внос "+nf.format(i.value)+" млн. евро.",host);}
 const g=latest(series(data,"gdp_real_growth"));if(g)kpi("eco-kpis",series(data,"gdp_per_capita_current_eur")," €","БВП на човек, текущи цени");
 const pop=valid(series(data,"population_total"));if(pop.length>1){const first=pop[0],last=pop[pop.length-1];const delta=last.value-first.value;const host=$("demo-kpis");const box=node("div",undefined,host,"c");node("div",(delta>0?"+":"")+n0.format(delta),box,"n");node("div","Промяна спрямо "+first.year,box,"l");node("div",last.year+" спрямо "+first.year,box,"s");}
 }catch(err){console.error("Неуспешно зареждане на икономическите серии",err);document.querySelectorAll("#eco-kpis,#lab-kpis,#eu-kpis,#demo-kpis,#trade-kpis").forEach(h=>{if(!h.children.length)node("p","Данните временно не са налични. Последната успешна версия се запазва.",h,"news-empty");});}
})();