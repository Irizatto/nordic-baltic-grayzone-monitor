const eventsPanel=document.getElementById('eventsPanel');
document.getElementById('eventsButton').addEventListener('click',()=>eventsPanel.classList.toggle('open'));
fetch('data/events.json').then(r=>r.json()).then(payload=>{
  const events=payload.events||[], filter=document.getElementById('eventFilter'), table=document.getElementById('eventsRows');
  [...new Set(events.map(event=>event.event_type))].sort().forEach(type=>filter.insertAdjacentHTML('beforeend','<option value="'+type+'">'+type.replaceAll('_',' ')+'</option>'));
  const render=()=>{const selected=filter.value;const rows=events.filter(event=>!selected||event.event_type===selected);table.innerHTML=rows.length?rows.map(event=>'<tr><td>'+event.date+'</td><td>'+event.region+'</td><td>'+event.event_type.replaceAll('_',' ')+'</td><td>'+event.risk_score+'</td><td>'+event.confidence+'</td><td>'+event.vessel_name+'</td></tr>').join(''):'<tr><td colspan="6">No research leads in this window. / 此窗口没有研究线索。</td></tr>';};
  filter.addEventListener('change',render);render();
}).catch(()=>{document.getElementById('eventsRows').innerHTML='<tr><td colspan="6">Event data unavailable. / 事件数据不可用。</td></tr>';});
