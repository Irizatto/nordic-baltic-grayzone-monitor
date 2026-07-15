window.escapeHtml=function(value){
  return String(value??'').replace(/[&<>'"]/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
};

document.querySelectorAll('.panel-toggle').forEach(button=>button.addEventListener('click',()=>{
  const open=button.parentElement.classList.toggle('open');
  button.setAttribute('aria-expanded',String(open));
}));
document.querySelectorAll('[data-layer]').forEach(input=>input.addEventListener('change',()=>{
  const group=window.groups?.[input.dataset.layer];
  if(!group){input.disabled=true;return;}
  if(input.checked)group.addTo(map);else map.removeLayer(group);
}));

window.showFeature=function(properties={}){
  const p=properties||{}, schematic=p.source==='manual_schematic'||p.route_precision==='schematic';
  document.getElementById('vesselDetail').innerHTML=
    '<div class="detail-row"><b>'+escapeHtml(p.name||'Unnamed feature / 未命名要素')+'</b>'+escapeHtml(p.category||'unknown')+'</div>'+
    '<div class="detail-row"><b>Data source / 数据来源</b>'+escapeHtml(p.source||'not supplied')+(p.source_url?' · '+escapeHtml(p.source_url):'')+'</div>'+
    '<div class="detail-row"><b>Last updated / 最后更新</b>'+escapeHtml(p.last_updated||'Not supplied / 未提供')+'</div>'+
    '<div class="detail-row"><b>Notes / 说明</b>'+escapeHtml(p.notes||'')+'</div>'+
    (schematic?'<p class="small">Schematic route or area: illustrative only, not a precise route, boundary, or operational position. / 示意路线或区域：仅作说明，并非精确路线、边界或运营位置。</p>':'');
  document.getElementById('detailPanel').classList.add('open');
};

window.showVessel=function(vessel={}){
  const v=vessel||{}, triggered=Array.isArray(v.triggered_rules)?v.triggered_rules:[];
  const shipType=String(v.ship_type||'unknown').trim().toLowerCase();
  const unscored=shipType==='naval'||shipType==='law_enforcement';
  const rules=triggered.length?triggered.map(rule=>
    '<div class="rule"><b>'+escapeHtml(String(rule.rule_id||'unknown').replaceAll('_',' '))+'</b>+'+escapeHtml(rule.points??0)+': '+escapeHtml(rule.evidence||'')+'</div>'
  ).join(''):'No triggered rules / 无触发规则';
  const level=String(v.risk_level||'Normal');
  const cssLevel=level.includes('Critical')?'critical':level.includes('High')?'high':level==='Watch'?'watch':'low';
  const nearest=(v.nearest_infrastructure&&typeof v.nearest_infrastructure==='object')?v.nearest_infrastructure:{};
  const distance=nearest.distance_km!==null&&nearest.distance_km!==undefined&&Number.isFinite(Number(nearest.distance_km))?nearest.distance_km:'not available / 不可用';
  document.getElementById('vesselDetail').innerHTML=
    '<div class="detail-row"><b>'+escapeHtml(v.name||'Unknown / 未知')+' · '+escapeHtml(v.mmsi||'')+'</b>'+escapeHtml(v.ship_type||'unknown')+' · '+escapeHtml(v.flag||'')+'</div>'+
    '<div class="detail-row"><b>Review priority / 审查优先级</b>'+(unscored?'<span class="risk risk-unscored">Not auto-scored / 不自动评分</span>':'<span class="risk risk-'+cssLevel+'">'+escapeHtml(v.risk_score??0)+' — '+escapeHtml(level)+'</span>')+'</div>'+
    '<div class="detail-row"><b>Motion / 动态</b>'+escapeHtml(v.speed??0)+' kn · course '+escapeHtml(v.course??0)+'° · heading '+escapeHtml(v.heading??0)+'°</div>'+
    '<div class="detail-row"><b>Nearest infrastructure / 最近基础设施</b>'+escapeHtml(nearest.name||'Not available')+' ('+escapeHtml(nearest.type||'not available')+'), '+escapeHtml(distance)+' km</div>'+
    '<div class="detail-row"><b>Data source / 数据来源</b>'+escapeHtml(v.source||'unknown')+'</div>'+
    '<div class="detail-row"><b>Risk signals / 风险信号</b>'+rules+'</div>';
  document.getElementById('detailPanel').classList.add('open');
};

