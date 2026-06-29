from flask import Flask, render_template, jsonify, request
import random
import time
import json
import requests
from datetime import datetime

app = Flask(__name__)

# === API KEY — shu yerga yozing ===
ANTHROPIC_API_KEY = ""

# === Sensor konfiguratsiyasi ===
SENSORS = [
    {"name": "Harorat",   "unit": "°C",    "normal": (60, 85),   "warning": (85, 100),  "critical": (100, 130)},
    {"name": "Bosim",     "unit": "bar",   "normal": (2.5, 4.5), "warning": (4.5, 6.0), "critical": (6.0, 8.0)},
    {"name": "Tezlik",    "unit": "rpm",   "normal": (1400,1600),"warning": (1600,1800), "critical": (1800,2200)},
    {"name": "Tok",       "unit": "A",     "normal": (8, 14),    "warning": (14, 18),   "critical": (18, 25)},
    {"name": "Vibrasiya", "unit": "mm/s",  "normal": (0.5, 2.5), "warning": (2.5, 5.0), "critical": (5.0, 10.0)},
    {"name": "Namlik",    "unit": "%",     "normal": (30, 60),   "warning": (60, 75),   "critical": (75, 95)},
]

state = {
    "fault_active": False,
    "fault_sensor": 0,
    "history": {i: [] for i in range(len(SENSORS))},
    "event_log": [],
    "chat_history": []
}

def generate_value(sensor_idx):
    s = SENSORS[sensor_idx]
    nmin, nmax = s["normal"]
    if state["fault_active"] and state["fault_sensor"] == sensor_idx:
        cmin, cmax = s["critical"]
        return round(random.uniform(cmin * 0.8, cmax), 2)
    base = random.uniform(nmin, nmax)
    noise = (nmax - nmin) * 0.03
    return round(base + random.uniform(-noise, noise), 2)

def get_status(value, sensor_idx):
    s = SENSORS[sensor_idx]
    nmin, nmax = s["normal"]
    wmin, wmax = s["warning"]
    if nmin <= value <= nmax:
        return "normal"
    elif wmin < value <= wmax:
        return "warning"
    else:
        return "critical"

def analyze_trend(history):
    """Trend tahlili — ko'tarilayaptimi yoki tushayaptimi"""
    if len(history) < 5:
        return "yetarli ma'lumot yo'q"
    vals = [h["value"] for h in history[-10:]]
    avg_first = sum(vals[:5]) / 5
    avg_last = sum(vals[-5:]) / 5
    diff = avg_last - avg_first
    pct = (diff / avg_first) * 100 if avg_first != 0 else 0
    if pct > 5:
        return f"ko'tarilmoqda (+{pct:.1f}%)"
    elif pct < -5:
        return f"tushmoqda ({pct:.1f}%)"
    else:
        return "barqaror"

def predict_fault(sensor_idx):
    """Buzilish ehtimolini bashorat qilish"""
    history = state["history"].get(sensor_idx, [])
    if len(history) < 5:
        return None
    s = SENSORS[sensor_idx]
    vals = [h["value"] for h in history[-15:]]
    nmax = s["normal"][1]
    cmax = s["critical"][1]
    current = vals[-1]
    trend = analyze_trend(history)

    if "ko'tarilmoqda" in trend and current > nmax * 0.9:
        risk = int(((current - nmax * 0.9) / (cmax - nmax * 0.9)) * 100)
        risk = min(95, max(10, risk))
        return {
            "sensor": s["name"],
            "risk": risk,
            "trend": trend,
            "message": f"{s['name']} sensori ko'tarilmoqda — buzilish ehtimoli {risk}%"
        }
    return None

def si_diagnose(readings):
    results = []
    for i, val in enumerate(readings):
        st = get_status(val, i)
        s = SENSORS[i]
        nmin, nmax = s["normal"]
        deviation = 0
        if val > nmax:
            deviation = ((val - nmax) / nmax) * 100
        elif val < nmin:
            deviation = ((nmin - val) / nmin) * 100
        if st != "normal":
            recs = {
                "Harorat": "Sovutish tizimini tekshiring, muftani ko'rib chiqing",
                "Bosim": "Bosim ventilini oching, quvur yo'lini tekshiring",
                "Tezlik": "Dvigatel yukini kamaytiring, tormoz tizimini tekshiring",
                "Tok": "Qisqa tutashuv xavfi! Zudlik bilan o'chiring",
                "Vibrasiya": "Podshipniklarni tekshiring, muvozanatlashni tekshiring",
                "Namlik": "Germetiklikni tekshiring, quritish tizimini ishga tushiring",
            }
            results.append({
                "sensor": s["name"],
                "value": val,
                "unit": s["unit"],
                "status": st,
                "deviation": round(deviation, 1),
                "recommendation": recs.get(s["name"], "Sensorni tekshiring")
            })
    return results

@app.route("/")
def index():
    return render_template("index.html", sensors=SENSORS, enumerate=enumerate)

@app.route("/api/sensors")
def api_sensors():
    readings = [generate_value(i) for i in range(len(SENSORS))]
    for i, val in enumerate(readings):
        state["history"][i].append({"time": time.time(), "value": val})
        if len(state["history"][i]) > 60:
            state["history"][i].pop(0)

    diagnostics = si_diagnose(readings)

    # Bashoratlar
    predictions = []
    for i in range(len(SENSORS)):
        p = predict_fault(i)
        if p:
            predictions.append(p)

    if diagnostics:
        event = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d.%m.%Y"),
            "issues": [f"{d['sensor']}: {d['status']}" for d in diagnostics]
        }
        state["event_log"].insert(0, event)
        if len(state["event_log"]) > 50:
            state["event_log"].pop()

    statuses = [get_status(r, i) for i, r in enumerate(readings)]
    system_status = "critical" if "critical" in statuses else "warning" if "warning" in statuses else "normal"

    return jsonify({
        "readings": [{
            "name": SENSORS[i]["name"],
            "unit": SENSORS[i]["unit"],
            "value": readings[i],
            "status": get_status(readings[i], i),
            "normal_min": SENSORS[i]["normal"][0],
            "normal_max": SENSORS[i]["normal"][1],
            "critical_max": SENSORS[i]["critical"][1],
            "trend": analyze_trend(state["history"][i]),
        } for i in range(len(SENSORS))],
        "diagnostics": diagnostics,
        "predictions": predictions,
        "system_status": system_status,
        "fault_active": state["fault_active"],
        "fault_sensor": state["fault_sensor"],
    })

@app.route("/api/fault", methods=["POST"])
def api_fault():
    data = request.json
    state["fault_active"] = data.get("active", False)
    state["fault_sensor"] = data.get("sensor", 0)
    return jsonify({"ok": True})

@app.route("/api/log")
def api_log():
    return jsonify(state["event_log"])

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    user_msg = data.get("message", "")
    readings = data.get("readings", [])
    diagnostics = data.get("diagnostics", [])
    predictions = data.get("predictions", [])

    sensor_summary = "\n".join([
        f"{r['name']}: {r['value']} {r['unit']} ({r['status']}) — trend: {r.get('trend','—')}"
        for r in readings
    ])
    diag_summary = "\n".join([
        f"{d['sensor']}: {d['status']} — {d['recommendation']}"
        for d in diagnostics
    ]) or "Barcha sensorlar normal"

    pred_summary = "\n".join([
        f"{p['sensor']}: buzilish ehtimoli {p['risk']}% — {p['trend']}"
        for p in predictions
    ]) or "Hozircha buzilish bashorati yo'q"

    system_prompt = f"""Sen avtomatlashtirish tizimlarining nosozliklarini diagnostika qiluvchi mutaxassis sun'iy intellektsан. O'zbek tilida qisqa, aniq va professional javob ber.

Hozirgi sensor holati:
{sensor_summary}

Diagnostika:
{diag_summary}

Buzilish bashorati:
{pred_summary}"""

    # Chat tarixini saqlash
    state["chat_history"].append({"role": "user", "content": user_msg})
    if len(state["chat_history"]) > 20:
        state["chat_history"] = state["chat_history"][-20:]

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": state["chat_history"]
            }
        )
        result = response.json()
        print("API javob:", result)
        if "content" in result:
            assistant_msg = result["content"][0]["text"]
            state["chat_history"].append({"role": "assistant", "content": assistant_msg})
            return jsonify({"reply": assistant_msg})
        elif "error" in result:
            err = result["error"]
            return jsonify({"reply": f"API xatolik: {err.get('type')} — {err.get('message')}"}), 400
        else:
            return jsonify({"reply": f"Noma'lum javob: {result}"}), 400
        state["chat_history"].append({"role": "assistant", "content": assistant_msg})
        return jsonify({"reply": assistant_msg})
    except Exception as e:
        return jsonify({"reply": f"Xatolik: {str(e)}"}), 500

if __name__ == "__main__":
    print("=" * 50)
    print("  AVTOMATLASHTIRISH DIAGNOSTIKA TIZIMI")
    print("  http://localhost:8080 da ishlamoqda")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8080, debug=True)

#  Bu kod Flask web serverini yaratadi, u real vaqtda sensor ma'lumotlarini simulyatsiya qiladi, nosozliklarni diagnostika qiladi, buzilish ehtimolini bashorat qiladi va foydalanuvchi bilan chat orqali muloqot qiladi. Chat funksiyasi uchun Anthropic API'sidan foydalaniladi, shuning uchun API kalitini to'g'ri o'rnatganingizga ishonch hosil qiling.
# http://localhost:8080 da ishlaydi. Sensor ma'lumotlari va diagnostika natijalari asosida foydalanuvchi savollariga javob beradi.