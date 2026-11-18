/* България в числа — статистически визуализации от проверени серии в economy.json */
(async function () {
 "use strict";
 const nf = new Intl.NumberFormat("bg-BG",{maximumFractionDigits:1});
 const n0 = new Intl.NumberFormat("bg-BG",{maximumFractionDigits:0});
 const $ = id => document.getElementById(id);
 const palette = {blue:"#426f9b",green:"#2d7963",red:"#ad514b",ochre:"#a87836",muted:"#65778c"};
 function node(tag, text, parent, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(parent)parent.appendChild(e); if(cls)e.className=cls; return e; }
 function series(data,id){return (data.series||[]).find(s=>s.id===id);}
 function valid(s){return s&&(s.points||[]).filter(p=>Number.isFinite(p.value)&&Number.isInteger(p.year)).sort((a,b)=>a.year-b.year);}
 function latest(s){const p=valid(s);return p.length?p[p.length-1]:null;}
 function kpi(hostId, s, suffix, label){const p=latest(s);if(!p)return;const box=node("div",undefined,$(hostId),"c");node("div",n0.format(p.value)+(suffix||""),box,"n");node("div",label||s.title,box,"l");node("div",String(p.year)+" · Евростат"+(p.flag==="p"?" · предварителни данни":p.flag==="e"?" · оценка":""),box,"s");}
 function kpiBillions(hostId,s,label){const p=latest(s);if(!p)return;const box=node("div",undefined,$(hostId),"c");node("div",new Intl.NumberFormat("bg-BG",{minimumFractionDigits:1,maximumFractionDigits:1}).format(p.value/1000)+" млрд. €",box,"n");node("div",label||s.title,box,"l");node("div",String(p.year)+" · Евростат"+(p.flag==="p"?" · предварителни данни":p.flag==="e"?" · оценка":""),box,"s");}
 function chart(hostId,s,color,unit){const host=$(hostId);if(!host||!s)return;const points=valid(s);if(points.length<2){node("p","Недостатъчно налични наблюдения.",host,"news-empty");return;}
 const W=720,H=250,L=62,R=18,T=18,B=38, vals=points.map(p=>p.value),lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo||Math.abs(hi)||1)*.14,min=lo-pad,max=hi+pad;
 const x=i=>L+i*(W-L-R)/(points.length-1), y=v=>T+(max-v)*(H-T-B)/(max-min);
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.setAttribute("role","img");svg.setAttribute("aria-label",s.title);host.appendChild(svg);
 function el(tag,attrs,txt){const e=document.createElementNS(svg.namespaceURI,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(txt!==undefined)e.textContent=txt;svg.appendChild(e);return e;}
 for(let i=0;i<=4;i++){const v=min+(max-min)*i/4;el("line",{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:"#dce4ec"});el("text",{x:L-8,y:y(v)+4,"text-anchor":"end"},nf.format(v));}
 const d=points.map((p,i)=>(i?"L":"M")+x(i)+" "+y(p.value)).join(" ");el("path",{d,fill:"none",stroke:color||palette.blue,"stroke-width":3,"stroke-linecap":"round","stroke-linejoin":"round"});
 const step=Math.max(1,Math.ceil(points.length/8));points.forEach((p,i)=>{const c=el("circle",{cx:x(i),cy:y(p.value),r:3.5,fill:color||palette.blue});const title=document.createElementNS(svg.namespaceURI,"title");title.textContent=p.year+": "+nf.format(p.value)+(unit||"");c.appendChild(title);if(i%step===0||i===points.length-1)el("text",{x:x(i),y:H-12,"text-anchor":"middle"},String(p.year));});
 const details=node("details",undefined,host);node("summary","Таблица с точните годишни стойности",details);const wrap=node("div",undefined,details,"tw"),table=node("table",undefined,wrap),thead=node("thead",undefined,table),tr=node("tr",undefined,thead);["Година","Стойност","Бележка"].forEach(t=>node("th",t,tr));const tb=node("tbody",undefined,table);points.forEach(p=>{const r=node("tr",undefined,tb);node("td",String(p.year),r);node("td",nf.format(p.value)+(unit||""),r);node("td",p.flag||"—",r);});
 }
 try{
 const res=await fetch("economy.json",{cache:"no-store"});if(!res.ok)throw Error("HTTP "+res.status);const data=await res.json();
 const regionNames={"region_gdp_pps_BG31":"Северозападен","region_gdp_pps_BG32":"Северен централен","region_gdp_pps_BG33":"Североизточен","region_gdp_pps_BG34":"Югоизточен","region_gdp_pps_BG41":"Югозападен","region_gdp_pps_BG42":"Южен централен"};
 const regions=Object.keys(regionNames).map(id=>({id,name:regionNames[id],point:latest(series(data,id))})).filter(x=>x.point);
 const regionHost=$("region-gdp-chart"),regionKpis=$("region-kpis");
 if(regions.length&&regionHost){
  const year=Math.min(...regions.map(x=>x.point.year));
  const comparable=regions.filter(x=>x.point.year===year).sort((a,b)=>b.point.value-a.point.value);
  const max=Math.max(...comparable.map(x=>x.point.value),1);
  const bars=node("div",undefined,regionHost);
  comparable.forEach((r,i)=>{const row=node("div",undefined,bars,"hb");node("span",r.name,row);const track=node("span",undefined,row,"t");const fill=node("i",undefined,track);fill.style.width=(r.point.value/max*100)+"%";fill.style.background=i===0?palette.green:palette.blue;node("b",nf.format(r.point.value),row);});
  node("p","Последна обща година за сравнение: "+year+" · PPS на жител.",regionHost,"src");
  if(regionKpis&&comparable.length){const best=comparable[0],worst=comparable[comparable.length-1],spread=best.point.value-worst.point.value,ratio=best.point.value/worst.point.value;const makeRegionCard=(value,label,note)=>{const box=node("div",undefined,regionKpis,"c");node("div",value,box,"n");node("div",label,box,"l");node("div",note,box,"s");};makeRegionCard(nf.format(best.point.value),"Най-висок показател · "+best.name,year+" · PPS на жител");makeRegionCard(nf.format(worst.point.value),"Най-нисък показател · "+worst.name,year+" · PPS на жител");makeRegionCard(nf.format(spread),"Разлика между най-високия и най-ниския",year+" · PPS на жител");makeRegionCard(ratio.toLocaleString("bg-BG",{minimumFractionDigits:2,maximumFractionDigits:2})+" пъти","Съотношение между двата крайни района",best.name+" спрямо "+worst.name); }
 }else if(regionHost){node("p","Регионалните данни временно не са налични. Ще се покажат след успешно потвърждение от Евростат.",regionHost,"news-empty");}
 const defs=[
 ["gdp_real_growth","eco-gdp-chart",palette.blue,"%"],
 ["gdp_per_capita_current_eur","eco-gdpcap-chart",palette.green," €"],
 ["employment_rate_20_64","lab-employment-chart",palette.green,"%"],
 ["unemployment_rate_15_74","lab-unemployment-chart",palette.red,"%"],
 ["gdp_pps_index","eu-ppp-chart",palette.ochre,""],
 ["population_total","demo-population-chart",palette.blue,""]
 ];
 defs.forEach(([id,target,color,unit])=>chart(target,series(data,id),color,unit));
 const ex=series(data,"exports_goods_mio_eur"),im=series(data,"imports_goods_mio_eur");
 if(ex&&im){
  const host=$("trade-chart"),a=valid(ex),b=valid(im),bm=new Map(b.map(p=>[p.year,p.value]));
  const rows=a.filter(p=>bm.has(p.year));
  if(rows.length){
   const last=rows[rows.length-1],imports=bm.get(last.year),balance=last.value-imports,coverage=last.value/imports*100;
   const balanceCard=node("div",undefined,$("trade-kpis"),"c "+(balance<0?"ac":"gr"));
   node("div",(balance<0?"−":"+")+nf.format(Math.abs(balance))+" млн. €",balanceCard,"n");
   node("div","Търговско салдо",balanceCard,"l");
   node("div",last.year+" · износ минус внос",balanceCard,"s");
   const coverageCard=node("div",undefined,$("trade-kpis"),"c bl");
   node("div",nf.format(coverage)+"%",coverageCard,"n");
   node("div","Покритие на вноса с износ",coverageCard,"l");
   node("div",last.year+" · износът спрямо вноса",coverageCard,"s");
  }
  if(host&&rows.length>1){
   const W=720,H=250,L=68,R=18,T=22,B=38,vals=rows.flatMap(p=>[p.value,bm.get(p.year)]),lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo||hi||1)*.12,min=lo-pad,max=hi+pad;
   const x=i=>L+i*(W-L-R)/(rows.length-1),y=v=>T+(max-v)*(H-T-B)/(max-min);
   const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.setAttribute("role","img");svg.setAttribute("aria-label","Износ и внос на стоки в милиони евро");host.appendChild(svg);
   function line(tag,attrs,txt){const e=document.createElementNS(svg.namespaceURI,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(txt!==undefined)e.textContent=txt;svg.appendChild(e);}
   for(let k=0;k<=4;k++){const v=min+(max-min)*k/4;line("line",{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:"#dce4ec"});line("text",{x:L-8,y:y(v)+4,"text-anchor":"end"},nf.format(v));}
   [[p=>p.value,palette.blue],[p=>bm.get(p.year),palette.red]].forEach(([get,color])=>{const d=rows.map((p,i)=>(i?"L":"M")+x(i)+" "+y(get(p))).join(" ");line("path",{d,fill:"none",stroke:color,"stroke-width":3,"stroke-linecap":"round","stroke-linejoin":"round"});});
   const step=Math.max(1,Math.ceil(rows.length/8));rows.forEach((p,i)=>{if(i%step===0||i===rows.length-1)line("text",{x:x(i),y:H-12,"text-anchor":"middle"},String(p.year));});
   line("text",{x:L,y:13,fill:palette.blue},"● Износ");line("text",{x:L+95,y:13,fill:palette.red},"● Внос");
   const last=rows[rows.length-1],bal=last.value-bm.get(last.year);node("p","Търговско салдо през "+last.year+": "+nf.format(bal)+" млн. евро.",host);
  }
 }
 kpi("eco-kpis",series(data,"gdp_real_growth"),"%","Реален растеж на БВП");
 kpi("lab-kpis",series(data,"employment_rate_20_64"),"%","Заетост, 20–64 г.");
 kpi("lab-kpis",series(data,"unemployment_rate_15_74"),"%","Безработица, 15–74 г.");
 const labHost=$("lab-kpis");
 const youth=node("div",undefined,labHost,"c ac");
 node("div","13,1%",youth,"n");
 node("div","Безработица сред младите, 15–24 г.",youth,"l");
 node("div","2025 · НСИ",youth,"s");
 const longTerm=node("div",undefined,labHost,"c am");
 node("div","1,5%",longTerm,"n");
 node("div","Продължителна безработица (1+ години)",longTerm,"l");
 node("div","2025 · НСИ",longTerm,"s");
 kpi("eu-kpis",series(data,"gdp_pps_index"),"","БВП на човек, ЕС = 100");
 const euHost=$("eu-kpis");
 const addEuCard=(value,label,note,cls)=>{const box=node("div",undefined,euHost,"c "+(cls||"bl"));node("div",value,box,"n");node("div",label,box,"l");node("div",note,box,"s");};
 addEuCard("72,3","Фактическо индивидуално потребление на човек","2025 · ЕС = 100 · Евростат","gr");
 addEuCard("63%","Ценово равнище на потреблението на домакинствата","2025 · ЕС = 100 · Евростат","am");
 addEuCard("+4,2 пр.п.","Потребление спрямо БВП на човек","72,3 − 68,1 · 2025 · процентни пункта","bl");
 kpi("demo-kpis",series(data,"population_total"),"","Население към 1 януари");
 kpi("trade-kpis",series(data,"exports_goods_mio_eur")," млн. €","Износ на стоки");
 kpi("trade-kpis",series(data,"imports_goods_mio_eur")," млн. €","Внос на стоки");
 const exp=series(data,"exports_goods_mio_eur"),imp=series(data,"imports_goods_mio_eur");
 if(exp&&imp){const host=$("trade-chart");const e=latest(exp),i=latest(imp);if(host&&e&&i)node("p","Последни налични стойности: износ "+nf.format(e.value)+" млн. евро; внос "+nf.format(i.value)+" млн. евро.",host);}
 const g=latest(series(data,"gdp_real_growth"));if(g)kpi("eco-kpis",series(data,"gdp_per_capita_current_eur")," €","БВП на човек, текущи цени");
 kpiBillions("eco-kpis",series(data,"exports_goods_mio_eur"),"Износ на стоки");
 kpiBillions("eco-kpis",series(data,"imports_goods_mio_eur"),"Внос на стоки");
 const pop=valid(series(data,"population_total"));if(pop.length>1){const first=pop[0],last=pop[pop.length-1];const delta=last.value-first.value;const host=$("demo-kpis");const box=node("div",undefined,host,"c");node("div",(delta>0?"+":"")+n0.format(delta),box,"n");node("div","Промяна спрямо "+first.year,box,"l");node("div",last.year+" спрямо "+first.year,box,"s");}
 const demoHost=$("demo-kpis");
 const ageing=node("div",undefined,demoHost,"c am");
 node("div","24,3%",ageing,"n");
 node("div","Население на 65 и повече години",ageing,"l");
 node("div","31.12.2025 · НСИ · 1 557 851 души",ageing,"s");
 const migration=node("div",undefined,demoHost,"c gr");
 node("div","+35 085",migration,"n");
 node("div","Положителен нетен външен миграционен прираст",migration,"l");
 node("div","2025 г. · НСИ · имигранти минус емигранти",migration,"s");
 }catch(err){console.error("Неуспешно зареждане на икономическите серии",err);document.querySelectorAll("#eco-kpis,#lab-kpis,#eu-kpis,#demo-kpis,#trade-kpis").forEach(h=>{if(!h.children.length)node("p","Данните временно не са налични. Последната успешна версия се запазва.",h,"news-empty");});}
})();