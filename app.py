"""Ecosystem - daraxtlar tizimi (Flask + SQLite). Ishga tushirish: python app.py"""
import os, sqlite3, time, base64, json, uuid, urllib.request, urllib.parse, urllib.error, threading, webbrowser, socket
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, session, send_from_directory, Response, g
from werkzeug.security import generate_password_hash as H, check_password_hash as C

# ================= SHU YERGA O'ZINGIZNING KALITLARINGIZNI YOZING =================
IMGBB_KEY = "f86359d7cc10323b164b0e67fa18335b"     # <-- imgbb.com API kaliti (rasmlar shu yerga yuklanadi; bo'sh bo'lsa serverda saqlanadi)
JSONBIN_ID = "6acf5b7eac6210605a3062d9"    # <-- JSONBin "BIN ID" (zaxira nusxa shu yerga yoziladi)
JSONBIN_KEY = "$2a$10$R3ZG0UPIq4CCKNJVSthT5urw1ftecBCfeOgTXWtCFRlbR9p12Ndeq"   # <-- JSONBin "X-Master-Key"
GEMINI_KEY = "AQ.Ab8RN6JuVes8M1tHGbb8GnBsboug2ZI5DfInHMwwq5AG7lyUhA"    # <-- Google AI Studio (aistudio.google.com) dagi Gemini API kaliti
GEMINI_MODEL = "gemini-3.5-flash"   # model nomi (ishlamasa "gemini-2.5-flash" deb yozing)
SECRET = "buni-uzun-matnga-almashtiring-987"   # <-- sessiya uchun maxfiy so'z
ADMIN_LOGIN = "tolibjon"   # birinchi ishga tushishdagi admin logini
ADMIN_PASS = "2008"        # birinchi ishga tushishdagi admin paroli (admin panelda almashtiriladi)
PUBLIC_URL = ""   # <-- haqiqiy sayt manzili, masalan https://ecosystem.uz (QR kodlar shu manzilni saqlaydi; bo'sh bo'lsa avtomatik aniqlanadi)
# ==================================================================================
IMGBB_KEY = os.getenv("IMGBB_KEY", IMGBB_KEY); JSONBIN_ID = os.getenv("JSONBIN_ID", JSONBIN_ID)
JSONBIN_KEY = os.getenv("JSONBIN_KEY", JSONBIN_KEY); SECRET = os.getenv("SECRET", SECRET); GEMINI_KEY = os.getenv("GEMINI_KEY", GEMINI_KEY)

PUBLIC_URL = os.getenv("PUBLIC_URL", PUBLIC_URL); PORT = int(os.getenv("PORT", 5000))
BASE = os.path.dirname(os.path.abspath(__file__))
DBF, UPD, STA = (os.path.join(BASE, x) for x in ("ecosystem.db", "uploads", "static"))
app = Flask(__name__, static_folder=None)
app.secret_key = SECRET
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
os.makedirs(UPD, exist_ok=True)
now = lambda: int(time.time())
err = lambda m, s=400: (jsonify({"err": m}), s)
ok = lambda x=None: jsonify(x if x is not None else {"ok": 1})


def db():
    if "d" not in g:
        g.d = sqlite3.connect(DBF); g.d.row_factory = sqlite3.Row
    return g.d


@app.teardown_appcontext
def close(e):
    d = g.pop("d", None)
    if d: d.close()


def init():
    c = sqlite3.connect(DBF)
    c.executescript("""
    create table if not exists users(id integer primary key autoincrement, ism, familya, yosh, kasb, login unique, pw, at);
    create table if not exists trees(id integer primary key autoincrement, uid, nomi, turi, yil, info, sugor, viloyat, shahar, tuman, manzil, lat, lng, imgs, at);
    create table if not exists logs(id integer primary key autoincrement, uid, at);
    create table if not exists cfg(k primary key, v);
    create table if not exists delreq(id integer primary key autoincrement, tid, uid, sabab, st, at);""")
    if not c.execute("select 1 from cfg where k='al'").fetchone():
        c.execute("insert into cfg values('al',?)", (ADMIN_LOGIN,)); c.execute("insert into cfg values('ap',?)", (H(ADMIN_PASS),))
    if "nav" not in {r[1] for r in c.execute("pragma table_info(trees)")}:
        c.execute("alter table trees add column nav")
    c.commit(); c.close()


init()
cfg = lambda k: db().execute("select v from cfg where k=?", (k,)).fetchone()[0]
adm = lambda: bool(session.get("admin"))


def me():
    u = session.get("u")
    return db().execute("select * from users where id=?", (u,)).fetchone() if u else None


def pub(u):
    return {k: u[k] for k in ("id", "ism", "familya", "yosh", "kasb", "login")}


def tr(r):
    d = dict(r); d["imgs"] = json.loads(d["imgs"] or "[]"); return d


UA = "Mozilla/5.0 (Ecosystem)"
SYNC = {"ok": None, "at": 0, "err": ""}
_lock = threading.Lock(); _dirty = False; _running = False
cloud_on = lambda: bool(JSONBIN_ID and JSONBIN_KEY)


def _jb(method, path, data=None):
    req = urllib.request.Request("https://api.jsonbin.io/v3/b/" + JSONBIN_ID + path,
          json.dumps(data).encode() if data is not None else None,
          {"Content-Type": "application/json", "X-Master-Key": JSONBIN_KEY, "X-Bin-Meta": "false",
           "User-Agent": UA, "Accept": "application/json"}, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=25))
    except urllib.error.HTTPError as e:
        raise Exception("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:150]))


def push():  # BARCHA ma'lumotni (foydalanuvchilar, daraxtlar, kirishlar, admin sozlamalari) JSONBin ga yozadi
    if not cloud_on(): return False
    try:
        c = sqlite3.connect(DBF); c.row_factory = sqlite3.Row
        s = {t: [dict(r) for r in c.execute("select * from " + t)] for t in ("users", "trees", "cfg", "delreq")}
        s["logs"] = [dict(r) for r in c.execute("select * from logs order by id desc limit 300")][::-1]; c.close()
        while len(json.dumps(s)) > 95000 and s["logs"]: s["logs"] = s["logs"][len(s["logs"]) // 2:]  # bepul tarif limiti ~100 KB
        _jb("PUT", "", s); SYNC.update(ok=True, at=now(), err="")
    except Exception as e:
        SYNC.update(ok=False, at=now(), err=str(e)[:200]); print("JSONBin xato:", e)
    return SYNC["ok"]


def _run():
    global _dirty, _running
    while True:
        with _lock:
            if not _dirty:
                _running = False; return
            _dirty = False
        push()


def backup():  # har o'zgarishdan keyin 2 soniyada JSONBin ga saqlaydi
    global _dirty, _running
    if not cloud_on(): return
    with _lock:
        _dirty = True
        if _running: return
        _running = True
    t = threading.Timer(2.0, _run); t.daemon = True; t.start()


def restore():  # baza bo'sh bo'lsa (masalan hosting o'chirib yuborsa), JSONBin dan hammasini qaytaradi
    if not cloud_on(): return
    c = sqlite3.connect(DBF)
    if c.execute("select 1 from users limit 1").fetchone() or c.execute("select 1 from trees limit 1").fetchone():
        c.close(); return
    try:
        r = _jb("GET", "/latest"); r = r.get("record", r)
        for t in ("users", "trees", "logs", "cfg", "delreq"):
            have = {x[1] for x in c.execute("pragma table_info(%s)" % t)}
            for row in r.get(t, []):
                cols = [k for k in row if k in have]
                c.execute("insert or replace into %s(%s) values(%s)" % (t, ",".join(cols), ",".join("?" * len(cols))), [row[k] for k in cols])
        c.commit(); print("JSONBin dan ma'lumotlar tiklandi")
    except Exception as e:
        print("JSONBin dan tiklashda xato:", e)
    c.close()


restore()


def save_img(b64):
    raw = base64.b64decode(b64.split(",")[-1])
    if IMGBB_KEY:
        try:
            data = urllib.parse.urlencode({"key": IMGBB_KEY, "image": base64.b64encode(raw)}).encode()
            return json.load(urllib.request.urlopen(urllib.request.Request("https://api.imgbb.com/1/upload", data, {"User-Agent": UA}), timeout=30))["data"]["url"]
        except Exception: pass
    n = uuid.uuid4().hex + ".jpg"
    open(os.path.join(UPD, n), "wb").write(raw)
    return "/uploads/" + n


# ---------- sahifalar ----------
def find(n):
    for d in (STA, BASE):
        p = os.path.join(d, n)
        if os.path.isfile(p): return p


def serve(n, mime):
    p = find(n)
    return Response(open(p, "rb").read(), mimetype=mime, headers={"Cache-Control": "no-cache"}) if p else None


@app.get("/")
def index():
    return serve("index.html", "text/html") or Response("<h2>static/index.html topilmadi</h2><p>Papka: %s</p>" % BASE, 500)


@app.get("/manifest.json")
def manifest():
    return serve("manifest.json", "application/json") or ("{}", 404)


@app.get("/sw.js")
def sw():
    return serve("sw.js", "text/javascript") or ("", 404)


@app.get("/icon-<int:n>.png")
def icon(n):
    return serve("icon-%d.png" % n, "image/png") or ("", 404)


@app.get("/uploads/<f>")
def up(f):
    return send_from_directory(UPD, f)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close()
        return ip
    except Exception:
        return ""


@app.get("/api/cfg")
def get_cfg():  # QR kodlar uchun manzil: PUBLIC_URL bo'lsa shu, bo'lmasa kompyuterning tarmoq (Wi-Fi) manzili
    ip = lan_ip()
    return ok({"base": PUBLIC_URL.rstrip("/"), "lan": ("%s:%d" % (ip, PORT)) if ip else ""})


# ---------- foydalanuvchilar ----------
@app.post("/api/register")
def register():
    d = request.json or {}
    l = d.get("login", "").strip().lower(); p = d.get("pw", "")
    if len(l) < 6 or len(p) < 6 or not d.get("ism", "").strip() or not d.get("familya", "").strip():
        return err("bad")
    if l == cfg("al").lower(): return err("exists")
    try:
        c = db().execute("insert into users(ism,familya,yosh,kasb,login,pw,at) values(?,?,?,?,?,?,?)",
                         (d["ism"].strip(), d["familya"].strip(), d.get("yosh"), (d.get("kasb") or "").strip()[:60], l, H(p), now()))
        db().commit()
    except sqlite3.IntegrityError:  # login band bo'lsa: parol mos kelsa, shunchaki tizimga kiritiladi
        u = db().execute("select * from users where login=?", (l,)).fetchone()
        if u and C(u["pw"], p):
            session.clear(); session["u"] = u["id"]
            db().execute("insert into logs(uid,at) values(?,?)", (u["id"], now())); db().commit(); backup()
            return ok()
        return err("exists")
    session.clear(); session["u"] = c.lastrowid
    db().execute("insert into logs(uid,at) values(?,?)", (c.lastrowid, now())); db().commit(); backup()
    return ok()


@app.post("/api/login")
def login():
    d = request.json or {}
    l = d.get("login", "").strip().lower(); p = d.get("pw", "")
    if l == cfg("al").lower():
        if C(cfg("ap"), p):
            session.clear(); session["admin"] = 1
            return ok({"role": "admin"})
        return err("wrong", 401)
    u = db().execute("select * from users where login=?", (l,)).fetchone()
    if not u or not C(u["pw"], p): return err("wrong", 401)
    session.clear(); session["u"] = u["id"]
    db().execute("insert into logs(uid,at) values(?,?)", (u["id"], now())); db().commit(); backup()
    return ok({"role": "user"})


@app.post("/api/logout")
def logout():
    session.clear(); return ok()


@app.get("/api/me")
def get_me():
    if adm(): return ok({"role": "admin", "login": cfg("al")})
    u = me()
    return ok({"role": "user", **pub(u)}) if u else err("no", 401)


@app.put("/api/me")
def put_me():
    u = me()
    if not u: return err("no", 401)
    d = request.json or {}
    l = d.get("login", u["login"]).strip().lower()
    if len(l) < 6 or l == cfg("al").lower(): return err("bad")
    try:
        db().execute("update users set ism=?,familya=?,yosh=?,kasb=?,login=? where id=?",
                     (d.get("ism", u["ism"]), d.get("familya", u["familya"]), d.get("yosh"), (d.get("kasb") or "").strip()[:60], l, u["id"]))
        if d.get("pw"):
            if len(d["pw"]) < 6: return err("bad")
            db().execute("update users set pw=? where id=?", (H(d["pw"]), u["id"]))
        db().commit()
    except sqlite3.IntegrityError:
        return err("exists")
    backup()
    return ok()


# ---------- daraxtlar ----------
@app.get("/api/trees")
def trees():
    rows = db().execute("select t.*,u.ism,u.familya from trees t left join users u on u.id=t.uid order by t.id desc").fetchall()
    return ok({"trees": [tr(r) for r in rows]})


@app.post("/api/trees")
def add_tree():
    u = me()
    if not u: return err("no", 401)
    d = request.json or {}
    imgs = [i for i in (d.get("imgs") or [])[:20] if i]
    if not imgs or not d.get("nomi", "").strip() or not d.get("viloyat", "").strip() or not d.get("shahar", "").strip():
        return err("bad")
    with ThreadPoolExecutor(5) as ex: urls = list(ex.map(save_img, imgs))
    c = db().execute("insert into trees(uid,nomi,nav,turi,yil,info,sugor,viloyat,shahar,tuman,manzil,lat,lng,imgs,at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (u["id"], d["nomi"].strip()[:100], (d.get("nav") or "").strip()[:100], d.get("turi"), d.get("yil"), (d.get("info") or "")[:4000], d.get("sugor"),
         d.get("viloyat"), d.get("shahar"), d.get("tuman"), d.get("manzil"), d.get("lat"), d.get("lng"), json.dumps(urls), now()))
    db().commit(); backup()
    return ok({"id": c.lastrowid})


@app.get("/api/me/delreq")
def my_delreq():
    u = me()
    if not u: return err("no", 401)
    return ok({"reqs": [dict(r) for r in db().execute("select tid,st,sabab,at from delreq where uid=?", (u["id"],))]})


@app.post("/api/trees/<int:i>/delreq")
def del_req(i):
    u = me()
    if not u: return err("no", 401)
    t = db().execute("select uid from trees where id=?", (i,)).fetchone()
    if not t or t["uid"] != u["id"]: return err("no", 403)
    s = ((request.json or {}).get("sabab") or "").strip()
    if len(s) < 5: return err("short")
    if db().execute("select 1 from delreq where tid=? and st='p'", (i,)).fetchone(): return err("pending", 409)
    db().execute("delete from delreq where tid=?", (i,))
    db().execute("insert into delreq(tid,uid,sabab,st,at) values(?,?,?,'p',?)", (i, u["id"], s[:1000], now()))
    db().commit(); backup()
    return ok()


# ---------- AI (Gemini) ----------
@app.post("/api/ai")
def ai():
    if not (adm() or me()): return err("no", 401)
    if not GEMINI_KEY: return err("ai_off", 503)
    d = request.json or {}
    rows = db().execute("select id,nomi,nav,turi,viloyat,shahar from trees order by id desc limit 40").fetchall()
    ctx = "Saytdagi daraxtlar: " + "; ".join("ECO-%05d %s %s (%s, %s)" % (r["id"], r["nomi"], r["nav"] or "", r["shahar"], r["viloyat"]) for r in rows)
    if d.get("tree"):
        t = db().execute("select * from trees where id=?", (d["tree"],)).fetchone()
        if t:
            ctx += "\nFoydalanuvchi hozir shu daraxtni ko'rmoqda: " + json.dumps({k: t[k] for k in ("id", "nomi", "nav", "turi", "yil", "info", "sugor", "viloyat", "shahar", "tuman", "manzil")}, ensure_ascii=False)
    system = ("Sen Ecosystem saytining AI yordamchisisan. Faqat daraxtlar, o'simliklar, ularni ekish, parvarish, sug'orish, kasalliklar, ekologiya va tabiatni asrash haqida javob ber; "
              "boshqa mavzularda muloyimlik bilan rad et. Qisqa, aniq va foydali yoz. Javob tili: %s.\n%s" % (str(d.get("lang") or "Uzbek")[:40], ctx))
    contents = [{"role": "model" if m.get("role") == "model" else "user", "parts": [{"text": str(m.get("text", ""))[:2000]}]} for m in (d.get("msgs") or [])[-10:]]
    if not contents or contents[-1]["role"] != "user": return err("bad")
    body = json.dumps({"systemInstruction": {"parts": [{"text": system}]}, "contents": contents}).encode()
    for model in dict.fromkeys([GEMINI_MODEL, "gemini-2.5-flash"]):
        try:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, body,
                                         {"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY, "User-Agent": UA})
            r = json.load(urllib.request.urlopen(req, timeout=45))
            parts = r["candidates"][0]["content"]["parts"]
            return ok({"text": "".join(p.get("text", "") for p in parts if not p.get("thought"))})
        except Exception as e:
            print("Gemini xato (%s):" % model, e)
    return err("ai_fail", 502)


# ---------- admin ----------
@app.get("/api/admin/users")
def a_users():
    if not adm(): return err("no", 403)
    out = []
    for u in db().execute("select * from users order by id desc"):
        ts = [tr(t) for t in db().execute("select * from trees where uid=? order by id desc", (u["id"],))]
        ll = db().execute("select max(at),count(*) from logs where uid=?", (u["id"],)).fetchone()
        out.append({**pub(u), "at": u["at"], "last": ll[0], "logins": ll[1], "trees": ts})
    logs = [dict(r) for r in db().execute("select l.at,u.ism,u.familya,u.login from logs l join users u on u.id=l.uid order by l.id desc limit 50")]
    reqs = [dict(r) for r in db().execute("select r.id,r.at,r.sabab,r.tid,t.nomi,t.imgs,u.ism,u.familya,u.login from delreq r "
            "join trees t on t.id=r.tid join users u on u.id=r.uid where r.st='p' order by r.id desc")]
    for r in reqs: r["imgs"] = json.loads(r["imgs"] or "[]")
    return ok({"users": out, "logs": logs, "reqs": reqs, "cloud": cloud_on(), "sync": SYNC})


@app.post("/api/admin/sync")
def a_sync():
    if not adm(): return err("no", 403)
    return ok({"ok": push(), "sync": SYNC})


@app.post("/api/admin/creds")
def a_creds():
    if not adm(): return err("no", 403)
    d = request.json or {}
    if len(d.get("login", "")) < 4 or len(d.get("pw", "")) < 4: return err("bad")
    db().execute("update cfg set v=? where k='al'", (d["login"].strip(),))
    db().execute("update cfg set v=? where k='ap'", (H(d["pw"]),)); db().commit(); backup()
    return ok()


@app.post("/api/admin/delreq/<int:i>")
def a_delreq(i):
    if not adm(): return err("no", 403)
    r = db().execute("select * from delreq where id=?", (i,)).fetchone()
    if not r: return err("nf", 404)
    if (request.json or {}).get("ok"):
        db().execute("delete from trees where id=?", (r["tid"],)); db().execute("delete from delreq where tid=?", (r["tid"],))
    else:
        db().execute("update delreq set st='r' where id=?", (i,))
    db().commit(); backup()
    return ok()


@app.delete("/api/admin/tree/<int:i>")
def a_del(i):
    if not adm(): return err("no", 403)
    db().execute("delete from trees where id=?", (i,)); db().execute("delete from delreq where tid=?", (i,)); db().commit(); backup()
    return ok()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:%d" % port)).start()
    print("Ecosystem: http://127.0.0.1:%d  (oynani yopmang)" % port)
    app.run(host="0.0.0.0", port=port, threaded=True)
