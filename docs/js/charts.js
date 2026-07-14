window.drawChart=function(counts){
  if(typeof window.Chart!=='function')return;
  new Chart(document.getElementById('riskChart'),{type:'bar',data:{labels:['Normal','Watch','High','Critical'],datasets:[{data:[counts.normal,counts.watch,counts.high,counts.critical],backgroundColor:['#6ee7b7','#facc15','#fb923c','#ef4444']}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#91a4bd',font:{size:9}},grid:{display:false}},y:{display:false}}}});
};
