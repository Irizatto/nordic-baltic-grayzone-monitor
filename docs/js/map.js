window.map=L.map('map',{zoomControl:false}).setView([59.5,21],5);
L.control.zoom({position:'bottomright'}).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}).addTo(map);
window.groups={vessels:L.layerGroup().addTo(map),official:L.layerGroup().addTo(map),sar:L.layerGroup().addTo(map),cables:L.layerGroup().addTo(map),pipelines:L.layerGroup().addTo(map),ports:L.layerGroup().addTo(map),windfarms:L.layerGroup().addTo(map),areas:L.layerGroup().addTo(map),helcom:L.layerGroup().addTo(map)};

const layerSettings={
  cables:{file:'cables.geojson',style:{color:'#00e5ff',weight:2,dashArray:'7 6',opacity:.9}},
  pipelines:{file:'pipelines.geojson',style:{color:'#fb923c',weight:3,opacity:.9}},
  ports:{file:'ports.geojson',point:true},
  windfarms:{file:'windfarms.geojson',style:{color:'#6ee7b7',weight:1,fillColor:'#00e5ff',fillOpacity:.16}},
  areas:{file:'sensitive_areas.geojson',style:{color:'#ef4444',weight:1,fillColor:'#ef4444',fillOpacity:.055,dashArray:'4 5'}},
  helcom:{file:'helcom_mpas.geojson',style:{color:'#7dd3a8',weight:1.2,fillColor:'#34d399',fillOpacity:.08,dashArray:'3 4'}}
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
    return {key,featureCount:features.length,properties:features.map(feature=>feature.properties||{})};
  });
}

const infrastructureLoads=Object.entries(layerSettings).map(([key,setting])=>addGeoJsonLayer(key,setting));
Promise.allSettled(infrastructureLoads).then(results=>{
  const loaded=results.filter(result=>result.status==='fulfilled'), failed=results.length-loaded.length;
  const loadedValues=loaded.map(result=>result.value);
  const properties=loadedValues.flatMap(result=>result.properties);
  const sources=[...new Set(properties.map(item=>item.source).filter(Boolean))];
  const dates=properties.map(item=>item.last_updated).filter(Boolean).sort();
  const realCount=properties.filter(item=>item.source==='emodnet_human_activities').length;
  const helcomCount=properties.filter(item=>item.source==='helcom_mads').length;
  const schematicCount=properties.filter(item=>item.source==='manual_schematic').length;
  const counts=Object.fromEntries(loadedValues.map(item=>[item.key,item.featureCount]));
  results.forEach((result,index)=>{
    if(result.status==='fulfilled')return;
    const key=Object.keys(layerSettings)[index], input=document.querySelector('[data-layer="'+key+'"]');
    if(input){input.disabled=true;input.closest('.layer-row')?.classList.add('unavailable');}
  });
  const status=document.getElementById('infrastructureStatus');
  const note=document.getElementById('infrastructureNote');
  if(!status)return;
  if(!loaded.length){
    status.textContent='Infrastructure layers unavailable; vessel dashboard remains functional. / 基础设施图层不可用；船舶仪表板仍可使用。';
    if(note)note.textContent='Infrastructure snapshots are unavailable; layer switches are disabled. / 基础设施快照不可用；相关图层开关已禁用。';
    return;
  }
  const degraded=failed?' · '+failed+' layer(s) unavailable / '+failed+' 个图层不可用':'';
  status.textContent='Infrastructure source / last updated: '+(sources.join(', ')||'not supplied')+' / '+(dates.at(-1)||'not supplied')+degraded+' / 基础设施来源与更新时间';
  if(note){
    const countText='Cables '+(counts.cables||0)+' · Pipelines '+(counts.pipelines||0)+' · Ports '+(counts.ports||0)+' · Wind farms '+(counts.windfarms||0)+' · Areas '+(counts.areas||0)+' · HELCOM MPAs '+(counts.helcom||0);
    note.textContent=countText+'. Public EMODnet: '+realCount+'; HELCOM MADS: '+helcomCount+'; labelled schematic supplements: '+schematicCount+'. Each switch controls its layer independently. / '+countText+'。EMODnet 公开数据：'+realCount+'；HELCOM MADS：'+helcomCount+'；标注的示意补充：'+schematicCount+'。每个开关可独立控制对应图层。';
  }
});
