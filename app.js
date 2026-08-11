const fmt=(v,d=1)=>v==null?'–':new Intl.NumberFormat('hu-HU',{maximumFractionDigits:d}).format(v);
const dateFmt=d=>d?new Intl.DateTimeFormat('hu-HU').format(new Date(d)):'–';
const last=s=>s?.length?s[s.length-1]:null;

const palette={lightBlue:'#1688f8',darkBlue:'#132fa8',orange:'#ff6b28',purple:'#5866c7'};
const common={
  animationDuration:500,
  grid:{left:66,right:90,top:52,bottom:68},
  tooltip:{trigger:'axis',valueFormatter:v=>fmt(v,2)},
  xAxis:{type:'category',axisLabel:{hideOverlap:true}},
  yAxis:{type:'value',scale:true},
  dataZoom:[{type:'inside'},{type:'slider',height:18,bottom:8}]
};

function chart(id,series,yName='',options={}){
  const el=document.getElementById(id);
  if(!el)return;
  const instance=echarts.init(el);
  const dates=[...new Set(series.flatMap(s=>s.data.map(x=>x.date)))].sort();
  instance.setOption({
    ...common,
    grid:{...common.grid,...(options.grid||{})},
    legend:{top:4,left:0},
    tooltip:{
      trigger:'axis',
      valueFormatter:v=>options.currency?`${fmt(v,0)} Ft`:options.decimals===0?fmt(v,0):fmt(v,2)
    },
    xAxis:{...common.xAxis,data:dates},
    yAxis:{...common.yAxis,name:yName,...(options.yAxis||{})},
    series:series.map(s=>({
      name:s.name,
      type:s.type||'line',
      showSymbol:false,
      smooth:options.smooth??true,
      connectNulls:true,
      endLabel:{show:true,formatter:p=>s.name,color:s.color},
      labelLayout:{moveOverlap:'shiftY'},
      itemStyle:{color:s.color},
      lineStyle:{width:2.5,color:s.color},
      areaStyle:s.area?{opacity:s.opacity??0.28,color:s.color}:undefined,
      data:dates.map(d=>{
        const x=s.data.find(v=>v.date===d);
        return x?x.value:null;
      })
    }))
  });
  addEventListener('resize',()=>instance.resize());
}

async function init(){
  const r=await fetch('data/dashboard.json',{cache:'no-store'});
  if(!r.ok)throw new Error('A dashboard.json nem érhető el');
  const d=await r.json();
  document.getElementById('updated').textContent='Adatfrissítés: '+dateFmt(d.updated_at);

  const cards=[
    ['Infláció',d.inflation,'%',1],['EUR/HUF',d.eurhuf,'Ft',2],['Brent',d.brent,'USD/hordó',2],
    ['Munkanélküliség',d.unemployment,'%',1],['GDP-növekedés',d.gdp,'%',1],['Alapkamat',d.base_rate,'%',2],
    ['Államadósság/GDP',d.debt,'%',1],['Folyó mérleg',d.current_account,'M EUR',0],
    ['Bruttó átlagkereset',d.earnings?.gross,'Ft',0]
  ];
  document.getElementById('kpis').innerHTML=cards.map(([n,s,u,p])=>{
    const x=last(s);return `<article class="kpi"><div class="kpi-label">${n}</div><div class="kpi-value">${fmt(x?.value,p)} <small>${u}</small></div><div class="kpi-date">${dateFmt(x?.date)}</div></article>`;
  }).join('');

  chart('chart-fx',[
    {name:'EUR/HUF',data:d.fx?.eurhuf||d.eurhuf,color:palette.lightBlue,area:true,opacity:.25},
    {name:'GBP/HUF',data:d.fx?.gbphuf||[],color:palette.darkBlue,area:true,opacity:.25},
    {name:'USD/HUF',data:d.fx?.usdhuf||[],color:palette.orange,area:true,opacity:.20}
  ],'Ft',{smooth:true,yAxis:{min:'dataMin'}});

  chart('chart-earnings',[
    {name:'Bruttó átlagkereset',data:d.earnings?.gross||[],color:palette.lightBlue,area:true,opacity:.34},
    {name:'Bruttó medián kereset',data:d.earnings?.median||[],color:palette.darkBlue,area:true,opacity:.28},
    {name:'Nettó átlagkereset',data:d.earnings?.net||[],color:palette.orange,area:true,opacity:.22}
  ],'Ft',{currency:true,smooth:true,yAxis:{min:'dataMin'}});

  chart('chart-prices',[
    {name:'Infláció %',data:d.inflation,color:'#ea1b2d'},
    {name:'Alapkamat %',data:d.base_rate_daily||d.base_rate,color:'#2563eb'}
  ],'%');
  chart('chart-labour',[
    {name:'Munkanélküliség %',data:d.unemployment,color:'#ea1b2d'},
    {name:'Foglalkoztatottság %',data:d.employment,color:'#0f9d76'}
  ],'%');
  chart('chart-gdp',[{name:'GDP éves változás %',data:d.gdp,color:'#2563eb',area:true}],'%');
  chart('chart-debt',[{name:'Államadósság/GDP %',data:d.debt,color:'#7c3aed',area:true}],'%');
  chart('chart-current',[{name:'Folyó mérleg',type:'bar',data:d.current_account,color:'#0f9d76'}],'M EUR',{decimals:0});
}

init().catch(e=>{document.querySelector('main').innerHTML=`<section class="panel"><h2>Az adatok még nem érhetők el</h2><p>${e.message}</p></section>`;console.error(e)});
