"""
IDM-proof, draggable in-app media player for the desktop app.
=============================================================

Why this module exists
----------------------
1. **No IDM popups.** Streamlit's st.audio/st.video serve the file over HTTP at
   /media/<hash>.<ext>; IDM sniffs that real, downloadable URL and pops "download
   this?" on every Play. We instead embed the bytes as a base64 ``data:`` payload
   and, in JS, turn it into a ``blob:`` that feeds a normal HTML5 element. IDM
   can't intercept blob:/data: (no request, no extension) — works in the browser
   AND WebView2 with zero IDM config.

2. **One unified player, so Expand never stops the music.** The mini bar and the
   full "now playing" view are the SAME iframe and the SAME <audio>/<video>
   element; Expand/Collapse is a pure in-page class toggle (no Streamlit rerun, no
   reload), so playback is uninterrupted. The only reload is an actual track
   change, after which the player restores its position, view and playback from
   ``sessionStorage``.

3. **It truly floats — drag it anywhere.** The header is a drag handle; while you
   drag, the iframe momentarily covers the viewport (transparent) to capture the
   mouse, then shrinks back to hug the card at its new spot. Position persists.

Server-side state (queue index, shuffle/repeat, close, openfile, queue jumps) is
changed by clicking hidden Streamlit buttons in the parent document — Streamlit
tags each widget container ``.st-key-<key>``. Pure string/byte helpers only (no
Streamlit import) so app.py can import it freely.
"""

import base64
import html
import os
import re

# Video larger than this opens in the OS player instead of embedding (also never
# triggers IDM — it isn't a browser fetch). Audio is always inlined.
INLINE_VIDEO_MAX = 75 * 1024 * 1024

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}

_MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".flac": "audio/flac", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".wma": "audio/x-ms-wma",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}

_REPEAT_ICON = {"off": "🔁", "all": "🔁", "one": "🔂"}


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXT


def mime_for(path):
    return _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def track_key(path):
    """A stable, JS/CSS-safe id for a file (sessionStorage keys are per-track)."""
    try:
        sig = f"{os.path.getmtime(path):.0f}"
    except OSError:
        sig = "0"
    base = re.sub(r"[^A-Za-z0-9]", "", os.path.basename(path))[-24:] or "track"
    return f"{base}{sig}"


def media_data_uri(path):
    """Whole file as a base64 ``data:`` URI — an IDM-proof media source. '' on fail."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        return f"data:{mime_for(path)};base64," + base64.b64encode(raw).decode("ascii")
    except OSError:
        return ""


def can_inline(path):
    try:
        if is_video(path):
            return os.path.getsize(path) <= INLINE_VIDEO_MAX
        return True
    except OSError:
        return False


def _thumb_html(thumb_uri, size, radius):
    if thumb_uri:
        return (f'<img src="{thumb_uri}" alt="" style="width:{size}px;height:{size}px;'
                f'border-radius:{radius}px;object-fit:cover;flex:0 0 auto;"/>')
    return (f'<div style="width:{size}px;height:{size}px;border-radius:{radius}px;'
            f'flex:0 0 auto;display:flex;align-items:center;justify-content:center;'
            f'font-size:{int(size * .42)}px;background:linear-gradient(135deg,#7C5CFF,#22D3EE);">🎵</div>')


def queue_items_html(items):
    """items: list of (queue_index, name, is_video, is_current)."""
    rows = []
    for qi, name, vid, cur in items:
        icon = "🔊" if cur else ("🎬" if vid else "🎵")
        cls = "q-item cur" if cur else "q-item"
        rows.append(f'<div class="{cls}" data-i="{qi}"><span>{icon}</span>'
                    f'<span class="qn">{html.escape(name)}</span></div>')
    return "".join(rows) or '<div class="q-empty">Just this track.</div>'


_STYLE = r"""
<style>
  *{box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
  html,body{margin:0;background:transparent;overflow:hidden}
  #mp{position:absolute;left:0;top:0;user-select:none}
  .card{background:rgba(18,13,33,.97);border:1px solid #2c2448;
    -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border-radius:18px;
    box-shadow:0 22px 54px -16px rgba(0,0,0,.72);color:#ECEAF6;overflow:hidden}
  #mp.mini .card{width:430px;padding:9px 11px 11px}
  #mp.full .card{width:386px;padding:13px 16px 12px}
  #mp.mini .full-view{display:none}
  #mp.full .mini-view{display:none}
  .drag{cursor:grab} .drag:active{cursor:grabbing}
  .t{font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .s{font-size:11px;color:#9a93b5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ic{background:transparent;border:none;color:#d8d3ee;cursor:pointer;border-radius:9px;
    padding:5px;font-size:15px;line-height:1;transition:.12s}
  .ic:hover{background:rgba(139,108,255,.2);color:#fff}
  .ic.sm{font-size:11px;padding:3px} .ic.big{font-size:21px}
  .pp{background:linear-gradient(135deg,#7C5CFF,#22D3EE);color:#fff;border:none;cursor:pointer;
    border-radius:50%;width:38px;height:38px;font-size:15px;display:flex;align-items:center;
    justify-content:center;flex:0 0 auto;transition:.12s}
  .pp.big{width:60px;height:60px;font-size:23px} .pp:hover{filter:brightness(1.13)}
  input[type=range]{-webkit-appearance:none;appearance:none;height:5px;border-radius:6px;
    background:#322a4d;outline:none;cursor:pointer}
  input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:13px;height:13px;
    border-radius:50%;background:linear-gradient(135deg,#8B6CFF,#22D3EE)}
  audio.med{display:none}
  #mp.mini video.med{position:absolute;width:2px;height:2px;opacity:0;pointer-events:none}
  #mp.full video.med{display:block;width:100%;max-height:280px;border-radius:14px;
    background:#000;margin-bottom:10px}
  .mini-view{display:flex;flex-direction:column;gap:7px}
  .mini-row{display:flex;align-items:center;gap:7px}
  .mini-row .drag{display:flex;align-items:center;gap:9px;flex:1;min-width:0}
  .meta{min-width:0;flex:1}
  .fhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
  .now{font-size:10px;letter-spacing:.13em;color:#8a83a8}
  .fart{display:flex;justify-content:center;margin-bottom:12px}
  .ftitle{font-weight:700;font-size:16px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .fsub{font-size:12.5px;color:#9a93b5;text-align:center;margin:2px 0 12px}
  .times{display:flex;justify-content:space-between;font-size:10.5px;color:#9a93b5;margin:4px 0 12px}
  .transport{display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px}
  .extras{display:flex;align-items:center;justify-content:center;gap:18px;margin-bottom:12px}
  .chip{background:transparent;border:1px solid #3a3158;color:#d8d3ee;border-radius:9px;
    padding:4px 11px;font-size:12px;cursor:pointer}
  .chip:hover{border-color:#8B6CFF}
  .vol{display:flex;align-items:center;gap:6px;color:#9a93b5;font-size:12px}
  .vol input{width:86px}
  .qhead{font-size:10px;letter-spacing:.12em;color:#8a83a8;margin:2px 0 6px}
  .queue{max-height:150px;overflow-y:auto;display:flex;flex-direction:column;gap:3px}
  .q-item{display:flex;align-items:center;gap:7px;padding:6px 9px;border-radius:9px;font-size:12.5px;
    cursor:pointer;color:#cfcadf}
  .q-item .qn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .q-item:hover{background:rgba(139,108,255,.16)}
  .q-item.cur{background:rgba(124,92,255,.22);color:#fff;font-weight:600}
  .q-empty{font-size:12px;color:#7a7397;padding:6px}
</style>
"""

_ENGINE = r"""
<script>
(function(){
  var KEY="@@KEY@@", SRC="@@SRC@@", ISVID="@@ISVID@@"==="1",
      INLINE="@@INLINE@@"==="1", REPEAT="@@REPEAT@@", ATEND="@@ATEND@@"==="1";
  var root=document.getElementById('mp');
  var med=document.getElementById('med');
  var fr=null; try{ fr=window.frameElement; }catch(e){}
  function PW(){ try{return window.parent.innerWidth;}catch(e){return 1200;} }
  function PH(){ try{return window.parent.innerHeight;}catch(e){return 800;} }
  function qa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function card(){ return document.querySelector('.card'); }

  function parentClick(k){
    try{ var b=window.parent.document.querySelector('.st-key-'+k+' button'); if(b) b.click(); }
    catch(e){}
  }

  function setFrame(x,y,w,h){
    if(!fr) return;
    fr.style.position='fixed'; fr.style.left=x+'px'; fr.style.top=y+'px';
    fr.style.width=w+'px'; fr.style.height=h+'px'; fr.style.zIndex=99990;
    fr.style.border='none'; fr.style.background='transparent';
  }
  function clamp(x,y,w,h){
    return { x:Math.max(4,Math.min(x,PW()-w-4)), y:Math.max(4,Math.min(y,PH()-h-4)) };
  }
  function fitFrame(){
    // size the iframe to hug the card, at the saved (or default) position
    var c=card(), w=c.offsetWidth, h=c.offsetHeight;
    var x=parseFloat(sessionStorage.getItem('mp_x')), y=parseFloat(sessionStorage.getItem('mp_y'));
    if(isNaN(x)||isNaN(y)){ x=PW()-w-18; y=PH()-h-18; }
    var cl=clamp(x,y,w,h);
    root.style.left='0'; root.style.top='0';
    setFrame(cl.x,cl.y,w,h);
    sessionStorage.setItem('mp_x',cl.x); sessionStorage.setItem('mp_y',cl.y);
  }

  // ---- expand / collapse: pure toggle, NO reload, audio keeps playing ----
  function setView(full){
    root.className = full ? 'full' : 'mini';
    sessionStorage.setItem('mp_exp', full?'1':'0');
    requestAnimationFrame(fitFrame);
  }
  var exp = sessionStorage.getItem('mp_exp');
  if(exp===null) exp = ISVID ? '1' : '0';
  root.className = exp==='1' ? 'full' : 'mini';

  // ---- audio engine (blob = IDM can't see it) ----
  var POSKEY='mp_pos_'+KEY;
  function fmt(t){ t=Math.max(0,Math.floor(t||0)); var m=Math.floor(t/60),s=t%60;
    return m+':'+(s<10?'0':'')+s; }
  function attach(url){
    med.src=url;
    med.addEventListener('loadedmetadata',function(){
      var p=parseFloat(sessionStorage.getItem(POSKEY)||'0');
      if(p>0&&isFinite(med.duration)&&p<med.duration-0.4){ try{med.currentTime=p;}catch(e){} }
      var w=sessionStorage.getItem('mp_playing');
      if(w===null||w==='1'){ med.play().catch(function(){}); }
    },{once:true});
  }
  if(SRC){
    fetch(SRC).then(function(r){return r.blob();})
      .then(function(b){ attach(URL.createObjectURL(b)); })
      .catch(function(){ attach(SRC); });
  }

  var sp=parseFloat(sessionStorage.getItem('mp_speed')||'1')||1; med.playbackRate=sp;
  var vol=parseFloat(sessionStorage.getItem('mp_vol')||'1'); if(isFinite(vol)) med.volume=vol;

  function syncPP(){ qa('.j-pp').forEach(function(b){ b.textContent=med.paused?'▶':'⏸'; }); }
  med.addEventListener('timeupdate',function(){
    if(isFinite(med.duration)&&med.duration>0){
      qa('.j-seek').forEach(function(s){ if(document.activeElement!==s)
        s.value=(med.currentTime/med.duration*1000).toFixed(0); });
      qa('.j-cur').forEach(function(e){ e.textContent=fmt(med.currentTime); });
      qa('.j-dur').forEach(function(e){ e.textContent=fmt(med.duration); });
      sessionStorage.setItem(POSKEY,med.currentTime);
    }
  });
  med.addEventListener('play', function(){ sessionStorage.setItem('mp_playing','1'); syncPP(); });
  med.addEventListener('pause',function(){ sessionStorage.setItem('mp_playing','0'); syncPP(); });
  med.addEventListener('ended',function(){
    if(REPEAT==='one'){ med.currentTime=0; med.play().catch(function(){}); }
    else if(ATEND){ sessionStorage.setItem('mp_playing','0'); med.currentTime=0; syncPP(); }
    else parentClick('mp_next');
  });
  qa('.j-seek').forEach(function(s){ s.addEventListener('input',function(){
    if(isFinite(med.duration)) med.currentTime=s.value/1000*med.duration; }); });
  qa('.j-pp').forEach(function(b){ b.addEventListener('click',function(){
    if(med.paused) med.play().catch(function(){}); else med.pause(); }); });
  qa('.j-prev').forEach(function(b){ b.addEventListener('click',function(){ parentClick('mp_prev'); }); });
  qa('.j-next').forEach(function(b){ b.addEventListener('click',function(){ parentClick('mp_next'); }); });
  qa('.j-close').forEach(function(b){ b.addEventListener('click',function(){
    sessionStorage.setItem('mp_playing','0'); parentClick('mp_close'); }); });
  qa('.j-shuffle').forEach(function(b){ b.addEventListener('click',function(){ parentClick('mp_shuffle'); }); });
  qa('.j-repeat').forEach(function(b){ b.addEventListener('click',function(){ parentClick('mp_repeat'); }); });
  qa('.j-expand').forEach(function(b){ b.addEventListener('click',function(){ setView(true); }); });
  qa('.j-collapse').forEach(function(b){ b.addEventListener('click',function(){ setView(false); }); });
  qa('.j-open').forEach(function(b){ b.addEventListener('click',function(){ parentClick('mp_openfile'); }); });

  var spd=document.querySelector('.j-speed');
  if(spd){ spd.addEventListener('click',function(){
    var steps=[1,1.25,1.5,2,0.75], i=steps.indexOf(med.playbackRate), nx=steps[(i+1)%steps.length];
    med.playbackRate=nx; sessionStorage.setItem('mp_speed',nx); spd.textContent=nx+'x'; });
    spd.textContent=med.playbackRate+'x'; }
  var vsl=document.querySelector('.j-vol');
  if(vsl){ vsl.value=(med.volume*100).toFixed(0); vsl.addEventListener('input',function(){
    med.volume=vsl.value/100; sessionStorage.setItem('mp_vol',med.volume); }); }

  var ql=document.querySelector('.queue');
  if(ql){ ql.addEventListener('click',function(e){
    var it=e.target.closest('.q-item'); if(it) parentClick('mpq_'+it.getAttribute('data-i')); }); }

  // ---- dragging: expand iframe to full viewport to capture the mouse ----
  var dragging=false, off=null, dW=0, dH=0;
  function onDown(e){
    if(e.button!==undefined && e.button!==0) return;
    if(e.target.closest('button') || e.target.closest('input')) return;  // let controls work
    dragging=true; off=null;
    var c=card(); dW=c.offsetWidth; dH=c.offsetHeight;
    var x=parseFloat(fr&&fr.style.left)||0, y=parseFloat(fr&&fr.style.top)||0;
    if(fr){ fr.style.left='0'; fr.style.top='0'; fr.style.width=PW()+'px'; fr.style.height=PH()+'px'; }
    root.style.left=x+'px'; root.style.top=y+'px';
    document.addEventListener('pointermove',onMove);
    document.addEventListener('pointerup',onUp);
    document.addEventListener('pointercancel',onUp);
    window.addEventListener('blur',onUp);            // released off-window -> don't get stuck
    e.preventDefault();
  }
  function onMove(e){
    if(!dragging) return;
    if(off===null) off={ dx:e.clientX-parseFloat(root.style.left||'0'),
                         dy:e.clientY-parseFloat(root.style.top||'0') };
    var nx=Math.max(0,Math.min(e.clientX-off.dx,PW()-dW));
    var ny=Math.max(0,Math.min(e.clientY-off.dy,PH()-dH));
    root.style.left=nx+'px'; root.style.top=ny+'px';
  }
  function onUp(){
    if(!dragging) return; dragging=false;
    document.removeEventListener('pointermove',onMove);
    document.removeEventListener('pointerup',onUp);
    document.removeEventListener('pointercancel',onUp);
    window.removeEventListener('blur',onUp);
    var fx=parseFloat(root.style.left||'0'), fy=parseFloat(root.style.top||'0');
    root.style.left='0'; root.style.top='0';
    setFrame(fx,fy,dW,dH);
    sessionStorage.setItem('mp_x',fx); sessionStorage.setItem('mp_y',fy);
  }
  qa('.drag').forEach(function(d){ d.addEventListener('pointerdown',onDown); });

  syncPP();
  requestAnimationFrame(fitFrame);
})();
</script>
"""


def _render(tokens, body):
    doc = _STYLE + body + _ENGINE
    for k, v in tokens.items():
        doc = doc.replace(k, v)
    return doc


def player_html(title, artist, thumb_uri, src, key, queue_html, *, is_vid=False,
                inlineable=True, shuffle=False, repeat="off", at_end=False):
    """The whole player: ONE iframe with a mini bar + an expandable full view that
    share a single <audio>/<video>. Expand/Collapse + dragging are in-page (no
    reload); transport / queue-jumps bridge to hidden Streamlit buttons."""
    if not inlineable:
        # Large video → plays in the OS player (also never triggers IDM). A dummy
        # audio element keeps the engine happy; the open button bridges out.
        media_root = '<audio id="med" class="med"></audio>'
        art_full = ('<div class="fart" style="flex-direction:column;gap:12px;color:#9a93b5;'
                    'text-align:center;padding:14px 8px"><div style="font-size:46px">🎬</div>'
                    '<div style="font-size:12.5px;max-width:280px">This video is large, so it '
                    'plays in your default player to stay smooth.</div>'
                    '<button class="pp j-open" style="width:auto;height:auto;border-radius:13px;'
                    'padding:10px 20px;font-size:13px">▶ Open in your player</button></div>')
    elif is_vid:
        media_root = ""
        art_full = '<video id="med" class="med" playsinline controls></video>'
    else:
        media_root = '<audio id="med" class="med"></audio>'
        art_full = f'<div class="fart">{_thumb_html(thumb_uri, 210, 18)}</div>'
    sh_col = "#22D3EE" if shuffle else "#6f678c"
    rp_col = "#22D3EE" if repeat != "off" else "#6f678c"
    rp_icon = _REPEAT_ICON.get(repeat, "🔁")
    t, a = html.escape(title), html.escape(artist)

    body = f"""
    <div id="mp" class="mini">
      <div class="card">
        {media_root}
        <div class="mini-view">
          <div class="mini-row">
            <div class="drag" title="Drag to move">
              {_thumb_html(thumb_uri, 46, 10)}
              <div class="meta"><div class="t">{t}</div><div class="s">{a}</div></div>
            </div>
            <button class="ic j-prev" title="Previous">⏮</button>
            <button class="pp j-pp" title="Play / pause">▶</button>
            <button class="ic j-next" title="Next">⏭</button>
            <button class="ic sm j-expand" title="Full player">⤢</button>
            <button class="ic sm j-close" title="Close">✕</button>
          </div>
          <input class="j-seek" type="range" min="0" max="1000" value="0">
        </div>
        <div class="full-view">
          <div class="drag fhead" title="Drag to move">
            <button class="ic j-collapse" title="Minimize">▾</button>
            <span class="now">NOW PLAYING · drag to move</span>
            <button class="ic j-close" title="Close">✕</button>
          </div>
          {art_full}
          <div class="ftitle">{t}</div>
          <div class="fsub">{a}</div>
          <input class="j-seek" type="range" min="0" max="1000" value="0">
          <div class="times"><span class="j-cur">0:00</span><span class="j-dur">0:00</span></div>
          <div class="transport">
            <button class="ic j-shuffle" title="Shuffle" style="color:{sh_col}">🔀</button>
            <button class="ic big j-prev" title="Previous">⏮</button>
            <button class="pp big j-pp" title="Play / pause">▶</button>
            <button class="ic big j-next" title="Next">⏭</button>
            <button class="ic j-repeat" title="Repeat: {repeat}" style="color:{rp_col}">{rp_icon}</button>
          </div>
          <div class="extras">
            <button class="chip j-speed" title="Playback speed">1x</button>
            <span class="vol">🔉<input class="j-vol" type="range" min="0" max="100" value="100"></span>
          </div>
          <div class="qhead">UP NEXT</div>
          <div class="queue">{queue_html}</div>
        </div>
      </div>
    </div>
    """
    tokens = {
        "@@KEY@@": key, "@@SRC@@": src, "@@ISVID@@": "1" if is_vid else "0",
        "@@INLINE@@": "1" if inlineable else "0", "@@REPEAT@@": repeat,
        "@@ATEND@@": "1" if at_end else "0",
    }
    return _render(tokens, body)
