window.map=L.map('map',{zoomControl:false}).setView([59.5,21],5);
L.control.zoom({position:'bottomright'}).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(map);
window.groups={vessels:L.layerGroup().addTo(map),sar:L.layerGroup().addTo(map),cables:L.layerGroup().addTo(map),pipelines:L.layerGroup().addTo(map),ports:L.layerGroup().addTo(map),windfarms:L.layerGroup().addTo(map),areas:L.layerGroup().addTo(map)};

const layerSettings={
  cables:{file:'cables.geojson',style:{color:'#00e5ff',weight:2,dashArray:'7 6',opacity:.9}},
  pipelines:{file:'pipelines.geojson',style:{color:'#fb923c',weight:3,opacity:.9}},
  ports:{file:'ports.geojson',point:true},
  windfarms:{file:'windfarms.geojson',style:{color:'#6ee7b7',weight:1,fillColor:'#00e5ff',fillOpacity:.16}},
  areas:{file:'sensitive_areas.geojson',style:{color:'#ef4444',weight:1,fillColor:'#ef4444',fillOpacity:.055,dashArray:'4 5'}}
};

function addGeoJsonLayer(key,setting){
  return fetch('data/layers/'+setting.file).then(response=>{if(!response.ok)throw new Error(setting.file+' returned '+response.status);return response.json();}).then(data=>{
    const features=Array.isArray(data.features)?data.features:[];
    L.geoJSON(data,{
      style:()=>setting.style,
      pointToLayer:(feature,latlng)=>L.circleMarker(latlng,{radius:4,color:'#e6f1ff',weight:1,fillColor:'#91a4bd',fillOpacity:.85}),
      onEachFeature:(feature,layer)=>{
        const label=document.createElement('span');
        label.textContent=String(feature.properties?.name||'Unnamed feature');
        layer.bindTooltip(label);
        layer.on('click',()=>window.showFeature(feature.properties||{}));
      }
    }).addTo(groups[key]);
    return features.map(feature=>feature.properties||{});
  });
}

const infrastructureLoads=Object.entries(layerSettings).map(([key,setting])=>addGeoJsonLayer(key,setting));
Promise.allSettled(infrastructureLoads).then(results=>{
  const loaded=results.filter(result=>result.status==='fulfilled'), failed=results.length-loaded.length;
  const properties=loaded.flatMap(result=>result.value);
  const sources=[...new Set(properties.map(item=>item.source).filter(Boolean))];
  const dates=properties.map(item=>item.last_updated).filter(Boolean).sort();
  const status=document.getElementById('infrastructureStatus');
  if(!status)return;
  if(!loaded.length){
    status.textContent='Infrastructure layers unavailable; vessel dashboard remains functional. / 基础设施图层不可用；船舶仪表板仍可使用。';
    return;
  }
  const degraded=failed?' · '+failed+' layer(s) unavailable / '+failed+' 个图层不可用':'';
  status.textContent='Infrastructure source / last updated: '+(sources.join(', ')||'not supplied')+' / '+(dates.at(-1)||'not supplied')+degraded+' / 基础设施来源与更新时间';
});
