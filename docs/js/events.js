const eventsPanel=document.getElementById('eventsPanel');
const eventsButton=document.getElementById('eventsButton');
const eventTypeLabels={
  cable_proximity:'Cable proximity / 电缆接近',pipeline_proximity:'Pipeline proximity / 管道接近',loitering:'Low-speed presence / 低速停留',ais_gap:'AIS gap / AIS 空档',identity_change:'Identity change / 身份变化',sar_unmatched:'Unmatched SAR / 未匹配 SAR',sts_rendezvous:'STS rendezvous lead / 船对船会合线索',sanctions_match:'Sanctions match / 制裁名单匹配',shadow_fleet_match:'Shadow-fleet match / 影子船队名单匹配',sensitive_area_repeat_presence:'Repeated sensitive-area presence / 敏感区域重复出现',news_matched_incident:'Public-report match / 公开报道匹配'
};
const confidenceLabels={low:'Low / 低',medium:'Medium / 中',high:'High / 高'};
eventsButton.addEventListener('click',()=>{
  const open=eventsPanel.classList.toggle('open');
  eventsButton.setAttribute('aria-expanded',String(open));
});

fetch('data/events.json').then(response=>{if(!response.ok)throw new Error('events.json unavailable');return response.json();}).then(payload=>{
  const inputEvents=Array.isArray(payload.events)?payload.events:[];
  const events=[...inputEvents].sort((left,right)=>String(right.date||'').localeCompare(String(left.date||''))||String(right.time||'').localeCompare(String(left.time||'')));
  const filter=document.getElementById('eventFilter'), table=document.getElementById('eventsRows');
  [...new Set(events.map(event=>String(event.event_type||'unknown')))].sort().forEach(type=>{
    const option=document.createElement('option');
    option.value=type;
    option.textContent=eventTypeLabels[type]||type.replaceAll('_',' ');
    filter.append(option);
  });
  const render=()=>{
    const selected=filter.value, rows=events.filter(event=>!selected||event.event_type===selected);
    table.innerHTML=rows.length?rows.map(event=>
      '<tr><td>'+escapeHtml(event.date||'')+'</td><td>'+escapeHtml(event.region||'')+'</td><td>'+escapeHtml(eventTypeLabels[event.event_type]||String(event.event_type||'unknown').replaceAll('_',' '))+'</td><td>'+escapeHtml(event.risk_score??0)+'</td><td>'+escapeHtml(confidenceLabels[event.confidence]||event.confidence||'unknown')+'</td><td>'+escapeHtml(event.vessel_name||'')+'</td></tr>'
    ).join(''):'<tr><td colspan="6">No research leads in this window. / 此窗口没有研究线索。</td></tr>';
  };
  filter.addEventListener('change',render);
  render();
}).catch(()=>{
  document.getElementById('eventsRows').innerHTML='<tr><td colspan="6">Event data unavailable. / 事件数据不可用。</td></tr>';
});
