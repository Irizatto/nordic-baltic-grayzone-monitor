const eventsPanel=document.getElementById('eventsPanel');
const eventsButton=document.getElementById('eventsButton');
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
    option.textContent=type.replaceAll('_',' ');
    filter.append(option);
  });
  const render=()=>{
    const selected=filter.value, rows=events.filter(event=>!selected||event.event_type===selected);
    table.innerHTML=rows.length?rows.map(event=>
      '<tr><td>'+escapeHtml(event.date||'')+'</td><td>'+escapeHtml(event.region||'')+'</td><td>'+escapeHtml(String(event.event_type||'unknown').replaceAll('_',' '))+'</td><td>'+escapeHtml(event.risk_score??0)+'</td><td>'+escapeHtml(event.confidence||'unknown')+'</td><td>'+escapeHtml(event.vessel_name||'')+'</td></tr>'
    ).join(''):'<tr><td colspan="6">No research leads in this window. / 此窗口没有研究线索。</td></tr>';
  };
  filter.addEventListener('change',render);
  render();
}).catch(()=>{
  document.getElementById('eventsRows').innerHTML='<tr><td colspan="6">Event data unavailable. / 事件数据不可用。</td></tr>';
});
