"""Generate clearly labelled fictional data for the static dashboard."""
from datetime import datetime, timezone
from config import DOCS_DATA
from utils_io import write_json

def vessel(mmsi, name, ship_type, lat, lon, score, level, rules, infra, **extra):
    return {"mmsi": mmsi, "imo": extra.get("imo", "IMO" + mmsi[-7:]), "name": name,
      "callsign": extra.get("callsign", "OX" + mmsi[-4:]), "flag": extra.get("flag", "Example Registry"),
      "ship_type": ship_type, "lat": lat, "lon": lon, "speed": extra.get("speed", 9.4),
      "course": extra.get("course", 82), "heading": extra.get("heading", 84),
      "timestamp": datetime.now(timezone.utc).isoformat(), "risk_score": score, "risk_level": level,
      "triggered_rules": rules, "nearest_infrastructure": infra, "source": "mock"}

def generate():
    existing = [DOCS_DATA / "data.json", DOCS_DATA / "events.json", DOCS_DATA / "metadata.json"]
    if any(path.exists() for path in existing):
        print("Mock data already exists; preserving existing dashboard data.")
        return
    now = datetime.now(timezone.utc).isoformat()
    cable = {"name":"Mock Gulf Fibre Link","type":"submarine cable","distance_km":1.8}
    vessels = [
      vessel("255100001","NORDIC HORIZON","tanker",59.78,24.42,91,"Critical Review Priority",[{"rule_id":"loitering_near_infrastructure","points":55,"evidence":"Low speed within 2 km of mock cable for 4 hours"}],cable,speed=0.7,course=12,flag="Example Registry A"),
      vessel("255100002","BALTIC WAY","cargo",59.92,25.63,63,"High Review Priority",[{"rule_id":"ais_gap","points":35,"evidence":"Mock AIS reporting gap of 6 hours"}],{"name":"Balticconnector Area","type":"pipeline","distance_km":8.2},speed=11.2),
      vessel("255100003","SEA LARK","service",57.55,18.31,58,"High Review Priority",[{"rule_id":"identity_change","points":32,"evidence":"Mock name and callsign change in recent track"}],{"name":"Gotland Array","type":"wind farm","distance_km":5.4},speed=4.2),
      vessel("255100004","GOTLAND TRADER","cargo",57.72,18.01,28,"Watch",[{"rule_id":"route_deviation","points":12,"evidence":"Mock route differs from recent pattern"}],{"name":"Visby Port","type":"port","distance_km":18.4}),
      vessel("255100005","SKANE STAR","tanker",55.42,14.78,41,"Watch",[{"rule_id":"slow_transit","points":15,"evidence":"Low-speed passage in mock sensitive area"}],{"name":"Bornholm Cable","type":"submarine cable","distance_km":7.1},speed=3.1),
      vessel("255100006","STRAIT RUNNER","cargo",55.71,11.22,18,"Low",[],{"name":"Danish Straits","type":"chokepoint","distance_km":14.0}),
      vessel("255100007","ARCTIC LENS","research",72.42,29.84,46,"Watch",[{"rule_id":"unusual_dwell","points":18,"evidence":"Mock prolonged dwell outside usual survey zone"}],{"name":"Barents Link","type":"submarine cable","distance_km":11.6},speed=2.0),
      vessel("255100008","NORTH CAPE","fishing",74.16,24.51,14,"Low",[],{"name":"Barents Sea North","type":"sensitive area","distance_km":25.7}),
      vessel("255100009","FJORD SERVICE","tug",63.48,4.96,22,"Low",[],{"name":"Norwegian Sea Platform","type":"pipeline","distance_km":19.2}),
      vessel("255100010","AURORA FREIGHT","cargo",69.95,18.43,33,"Watch",[{"rule_id":"night_speed_change","points":10,"evidence":"Mock speed pattern change"}],{"name":"Tromso Port","type":"port","distance_km":12.5}),
      vessel("255100011","BORN SOUND","unknown",55.12,15.63,52,"High Review Priority",[{"rule_id":"incomplete_identity","points":24,"evidence":"Mock incomplete identity fields"}],{"name":"Bornholm Area","type":"sensitive area","distance_km":3.6}),
      vessel("255100012","HELSINKI MERCHANT","cargo",60.12,24.98,9,"Low",[],{"name":"Helsinki Port","type":"port","distance_km":7.8}),
    ]
    sar = [{"id":"SAR-001","lat":59.80,"lon":24.45,"matched_mmsi":"255100001","confidence":"mock high"},{"id":"SAR-002","lat":55.20,"lon":15.90,"matched_mmsi":None,"confidence":"mock medium"},{"id":"SAR-003","lat":72.50,"lon":29.90,"matched_mmsi":None,"confidence":"mock low"}]
    write_json(DOCS_DATA / "data.json", {"metadata":{"generated_at":now,"mode":"mock","sources":["mock"]},"vessels":vessels,"sar_detections":sar})
    write_json(DOCS_DATA / "events.json", {"metadata":{"generated_at":now,"mode":"mock"},"events":[]})
    write_json(DOCS_DATA / "metadata.json", {"generated_at":now,"mode":"mock","sources":["mock"],"fallbacks":["No live data sources are configured in this stage; dashboard is using fictional mock data."]})

if __name__ == "__main__": generate()
