/* Welcome screen: a slow liquid mass behind the title.
   Two motions are layered. The first is the mass breathing on its own —
   four sine waves of different frequency over the angle, so the outline
   never repeats within a visit. The second is the pointer: the side facing
   the cursor swells toward it and the whole body drifts a little that way.
   Canvas, one rAF loop, nothing per-frame allocated. */
(function(){
  "use strict";
  var cv = document.getElementById("blob");
  if(!cv || !cv.getContext) return;
  var ctx = cv.getContext("2d");
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var TAU = Math.PI*2, P = 110;
  var W=0, H=0, DPR=1, base=0;
  var px=0, py=0, has=false;          // pointer, in canvas space
  var dx=0, dy=0;                     // eased drift of the body
  var pull=0;                         // eased strength of the pointer
  var pts = new Float64Array(P*2);

  function size(){
    var r = cv.getBoundingClientRect();
    DPR = Math.min(window.devicePixelRatio||1, 2);
    W = Math.max(1, Math.round(r.width));
    H = Math.max(1, Math.round(r.height));
    cv.width = W*DPR; cv.height = H*DPR;
    ctx.setTransform(DPR,0,0,DPR,0,0);
    base = Math.min(W,H) * (W < 700 ? 0.40 : 0.33);
  }

  function shape(t){
    var cx = W/2 + dx, cy = H/2 + dy;
    var pa = 0, pd = 0;
    if(has){
      var ox = px - cx, oy = py - cy;
      pd = Math.sqrt(ox*ox + oy*oy);
      pa = Math.atan2(oy, ox);
    }
    for(var i=0;i<P;i++){
      var a = i/P * TAU;
      var rr = 1
        + 0.105*Math.sin(a*3 + t*0.00042)
        + 0.070*Math.sin(a*5 - t*0.00031)
        + 0.052*Math.sin(a*2 + t*0.00057)
        + 0.038*Math.cos(a*7 + t*0.00023);
      if(has && pull > 0.01){
        /* angular distance to the pointer, 0 = facing it */
        var da = a - pa;
        da = Math.abs(Math.atan2(Math.sin(da), Math.cos(da)));
        var face = Math.exp(-(da*da)/0.55);           // narrow bulge
        var near = 1 / (1 + Math.pow(pd/(base*1.35), 2));
        rr += 0.30 * face * near * pull;
        rr -= 0.06 * (1-face) * near * pull;          // the far side gives way
      }
      var r = base * rr;
      pts[i*2]   = cx + Math.cos(a)*r;
      pts[i*2+1] = cy + Math.sin(a)*r;
    }
  }

  function path(){
    ctx.beginPath();
    var mx = (pts[(P-1)*2] + pts[0]) / 2,
        my = (pts[(P-1)*2+1] + pts[1]) / 2;
    ctx.moveTo(mx, my);
    for(var i=0;i<P;i++){
      var j = (i+1) % P;
      var cxp = pts[i*2], cyp = pts[i*2+1];
      var ex = (cxp + pts[j*2]) / 2, ey = (cyp + pts[j*2+1]) / 2;
      ctx.quadraticCurveTo(cxp, cyp, ex, ey);
    }
    ctx.closePath();
  }

  function draw(t){
    ctx.clearRect(0,0,W,H);
    shape(t);
    var cx = W/2 + dx, cy = H/2 + dy;

    /* rim glow — the light the mass sits in */
    ctx.save();
    ctx.shadowColor = "rgba(243,100,88,.13)";
    ctx.shadowBlur  = Math.max(40, base*0.55);
    path();
    ctx.fillStyle = "#151515";
    ctx.fill();
    ctx.restore();

    /* body: lit from the upper left, falling away to the canvas colour */
    var g = ctx.createRadialGradient(
      cx - base*0.45, cy - base*0.55, base*0.08,
      cx, cy, base*1.30);
    g.addColorStop(0,   "#323232");
    g.addColorStop(0.55,"#212121");
    g.addColorStop(1,   "#121212");
    path();
    ctx.fillStyle = g;
    ctx.fill();

    /* a thin edge so the silhouette stays readable on dark */
    ctx.strokeStyle = "rgba(255,255,255,.075)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  var raf = 0, last = 0;
  function frame(t){
    raf = requestAnimationFrame(frame);
    if(t - last < 1000/45) return;      /* 45 fps is plenty for this */
    last = t;
    var tx = has ? (px - W/2) * 0.055 : 0;
    var ty = has ? (py - H/2) * 0.055 : 0;
    dx += (tx - dx) * 0.045;
    dy += (ty - dy) * 0.045;
    pull += ((has ? 1 : 0) - pull) * 0.06;
    draw(t);
  }

  function still(){ dx=dy=0; pull=0; has=false; draw(0); }

  function onMove(e){
    var r = cv.getBoundingClientRect();
    px = e.clientX - r.left; py = e.clientY - r.top;
    has = true;
  }

  size();
  if(reduce){
    still();
  }else{
    draw(0);
    raf = requestAnimationFrame(frame);
    /* pointer only where there is one — a finger should not drag the mass */
    if(window.matchMedia && window.matchMedia("(hover:hover)").matches){
      window.addEventListener("mousemove", onMove, {passive:true});
      document.addEventListener("mouseleave", function(){ has=false; });
    }
    document.addEventListener("visibilitychange", function(){
      if(document.hidden){ cancelAnimationFrame(raf); raf=0; }
      else if(!raf){ last=0; raf=requestAnimationFrame(frame); }
    });
  }
  window.addEventListener("resize", function(){ size(); if(reduce) still(); });
  window.addEventListener("orientationchange", function(){ size(); if(reduce) still(); });

  /* the line above the title types itself out, then holds */
  var el = document.getElementById("wtype");
  if(el){
    var full = el.getAttribute("data-text") || "";
    if(reduce){ el.textContent = full; }
    else{
      var k = 0;
      (function tick(){
        el.textContent = full.slice(0, k);
        if(k++ <= full.length) setTimeout(tick, 42);
      })();
    }
  }
})();
