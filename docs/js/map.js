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
  fetch('data/layers/'+setting.file).then(response=>response.json()).then(data=>{
    L.geoJSON(data,{
      style:()=>setting.style,
      pointToLayer:(feature,latlng)=>L.circleMarker(latlng,{radius:4,color:'#e6f1ff',weight:1,fillColor:'#91a4bd',fillOpacity:.85}),
      onEachFeature:(feature,layer)=>{
        layer.bindTooltip(feature.properties.name);
        layer.on('click',()=>window.showFeature(feature.properties));
      }
    }).addTo(groups[key]);
    const status=document.getElementById('infrastructureStatus');
    if(status){status.textContent='Infrastructure source / 最后更新: manual schematic / 2026-07-11';}
  }).catch(()=>console.warn('Could not load '+setting.file+'; mock vessel dashboard remains available.'));
}
Object.entries(layerSettings).forEach(([key,setting])=>addGeoJsonLayer(key,setting));
