const colors={Low:'#6ee7b7',Watch:'#facc15','High Review Priority':'#fb923c','Critical Review Priority':'#ef4444'};
const statusColor={ok:'green',credentials_missing_fallback_mock:'yellow',error_kept_old_data:'red'};
fetch('data/data.json').then(r=>r.json()).then(data=>{
  document.getElementById('updated').textContent='Updated / 更新: '+new Date(data.metadata.generated_at).toLocaleString();
  document.getElementById('mode').textContent=data.metadata.mode==='mock'?'MOCK DATA / 模拟数据':'MIXED DATA / 混合数据';
  const statuses=data.metadata.source_status||{};
  document.getElementById('sourceStatus').innerHTML=Object.entries(statuses).map(([name,info])=>'<span class="source-dot '+(statusColor[info.status]||'yellow')+'" title="'+name+': '+info.status+'"></span>'+name).join(' ');
  const counts={low:0,watch:0,high:0,critical:0};
  data.vessels.forEach(v=>{let k=v.risk_level.includes('Critical')?'critical':v.risk_level.includes('High')?'high':v.risk_level==='Watch'?'watch':'low';counts[k]++;const icon=L.divIcon({className:'vessel-icon',html:'<div class="vessel-dot" style="color:'+colors[v.risk_level]+';background:'+colors[v.risk_level]+'"></div>',iconSize:[14,14]});L.marker([v.lat,v.lon],{icon}).on('click',()=>showVessel(v)).addTo(groups.vessels)});
  data.sar_detections.forEach(s=>L.marker([s.lat,s.lon],{icon:L.divIcon({className:'sar-icon',html:'⌖',iconSize:[20,20]})}).bindTooltip('Mock SAR '+s.id+': '+(s.matched_mmsi?'matched':'unmatched')).addTo(groups.sar));
  document.getElementById('total').textContent=data.vessels.length;Object.keys(counts).forEach(k=>document.getElementById(k).textContent=counts[k]);document.getElementById('unmatched').textContent=data.sar_detections.filter(s=>!s.matched_mmsi).length;drawChart(counts)
}).catch(()=>{document.getElementById('updated').textContent='Data unavailable / 数据不可用';});
