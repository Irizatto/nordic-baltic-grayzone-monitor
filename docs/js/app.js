const colors={Normal:'#6ee7b7',Low:'#6ee7b7',Watch:'#facc15','High Review Priority':'#fb923c','Critical Review Priority':'#ef4444'};
const statusColor={ok:'green',credentials_missing_fallback_mock:'yellow',error_kept_old_data:'red'};

function fetchJson(path){
  return fetch(path,{cache:'no-store'}).then(response=>{if(!response.ok)throw new Error(path+' returned '+response.status);return response.json();});
}

function renderSourceStatus(statuses){
  const container=document.getElementById('sourceStatus');
  container.replaceChildren();
  Object.entries(statuses||{}).forEach(([name,info])=>{
    const dot=document.createElement('span');
    dot.className='source-dot '+(statusColor[info?.status]||'yellow');
    dot.title=name+': '+String(info?.status||'unknown')+(info?.detail?' — '+String(info.detail):'');
    const label=document.createTextNode(name+' ');
    container.append(dot,label);
  });
}

fetchJson('data/data.json').then(data=>
  Promise.all([Promise.resolve(data),fetchJson('data/metadata.json').catch(()=>data.metadata||{})])
).then(([data,publishedMetadata])=>{
  const embedded=data.metadata&&typeof data.metadata==='object'?data.metadata:{};
  const metadata={...embedded,...(publishedMetadata||{}),source_status:(publishedMetadata||{}).source_status||embedded.source_status||{}};
  const vessels=Array.isArray(data.vessels)?data.vessels:[];
  const sarDetections=Array.isArray(data.sar_detections)?data.sar_detections:[];
  const generatedAt=metadata.generated_at?new Date(metadata.generated_at):null;
  document.getElementById('updated').textContent='Updated / 更新: '+(generatedAt&&!Number.isNaN(generatedAt.valueOf())?generatedAt.toLocaleString():'not supplied / 未提供');
  const mode=document.getElementById('mode');
  mode.hidden=metadata.mode!=='mock';
  mode.textContent='MOCK DATA / 模拟数据';
  renderSourceStatus(metadata.source_status);
  const sourceNames=Array.isArray(metadata.sources)?metadata.sources:[];
  document.getElementById('dataSourceStatus').textContent='Data source / last updated: '+(sourceNames.join(', ')||'not supplied')+' / '+(metadata.generated_at||'not supplied')+' / 数据来源与更新时间';

  const counts={normal:0,watch:0,high:0,critical:0};
  let officialCount=0;
  vessels.forEach(vessel=>{
    const lat=Number(vessel.lat), lon=Number(vessel.lon);
    const shipType=String(vessel.ship_type||'unknown').trim().toLowerCase();
    const unscored=shipType==='naval'||shipType==='law_enforcement';
    const level=String(vessel.risk_level||'Normal');
    const key=level.includes('Critical')?'critical':level.includes('High')?'high':level==='Watch'?'watch':'normal';
    if(unscored)officialCount++;else counts[key]++;
    if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    const color=unscored?'#94a3b8':(colors[level]||colors.Normal);
    const markerClass=unscored?'vessel-dot unscored-dot':'vessel-dot';
    const icon=L.divIcon({className:'vessel-icon',html:'<div class="'+markerClass+'" style="color:'+color+';background:'+color+'"></div>',iconSize:[14,14]});
    L.marker([lat,lon],{icon}).on('click',()=>showVessel(vessel)).addTo(unscored?groups.official:groups.vessels);
  });
  sarDetections.forEach(detection=>{
    const lat=Number(detection.lat), lon=Number(detection.lon);
    if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    const matched=Boolean(detection.matched);
    const marker=L.circleMarker([lat,lon],{radius:matched?5:7,color:matched?'#7893a8':'#d7e4e9',weight:matched?1:2,fillColor:matched?'#526f86':'#b9d4dc',fillOpacity:matched?.75:.15,dashArray:matched?null:'3 3',className:matched?'sar-matched':'sar-ghost'});
    const gridNote=detection.source==='gfw_sar'?' GFW report coordinates are grid-cell centres, not precise individual positions. / GFW 报告坐标为网格中心，并非单个目标的精确位置。':'';
    marker.bindTooltip('SAR detection; a lead for review, not confirmation of illicit activity. / SAR 探测：供人工审查的线索，并非非法活动确认。'+gridNote).addTo(groups.sar);
  });
  document.getElementById('total').textContent=vessels.length;
  document.getElementById('sarTotal').textContent=sarDetections.length;
  document.getElementById('official').textContent=officialCount;
  Object.keys(counts).forEach(key=>document.getElementById(key).textContent=counts[key]);
  document.getElementById('unmatched').textContent=sarDetections.filter(detection=>!detection.matched).length;
  try{if(typeof window.drawChart==='function')window.drawChart(counts);}catch(error){console.warn('Risk chart unavailable; map data remains visible.',error);}
}).catch(error=>{
  console.error(error);
  document.getElementById('updated').textContent='Data unavailable / 数据不可用';
  document.getElementById('dataSourceStatus').textContent='Data source unavailable / 数据源不可用';
});
