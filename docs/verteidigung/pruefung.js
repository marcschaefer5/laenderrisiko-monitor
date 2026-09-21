/* Scroll-driven motion for the check page.
   One rAF-throttled pass over the pinned tracks; every track maps its own
   scroll progress to CSS custom properties. Transform and opacity only. */
(function(){
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- helpers ---------- */
  function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
  function seg(x,a,b){ return clamp((x-a)/(b-a),0,1); }
  function ease(t){ return t*t*(3-2*t); }
  function lerp(a,b,t){ return a+(b-a)*t; }
  var NEG = "−";                       // minus sign, not a hyphen
  function num(v,d){ var s=Math.abs(v).toFixed(d); return (v<0?NEG:"")+s; }

  /* ---------- chapter rail ---------- */
  var STEPS=["01","02","03","04"];
  document.querySelectorAll(".rail").forEach(function(rail){
    var mine=parseInt(rail.dataset.rail,10);
    rail.innerHTML = STEPS.map(function(s,i){
      var cls = i===mine ? "on" : (i<mine ? "done" : "");
      return '<span class="'+cls+'">'+s+'</span>';
    }).join("");
  });

  /* ---------- 01 · the value against the chance line ---------- */
  /* The column runs from 0.400 to 0.600; the dashed line at the middle is
     0.500. The fill stops at 0.508 — a hair past it, well inside the interval. */
  var LO=0.400, HI=0.600, VAL=0.508;
  function act1(p){
    var m=document.getElementById("meter"); if(!m) return;
    var g=ease(seg(p,.10,.70));
    m.style.setProperty("--g", g.toFixed(4));
    m.style.setProperty("--lo", String(ease(seg(p,.30,.50))));
    var v=document.getElementById("mval");
    if(v) v.textContent = lerp(LO,VAL,g).toFixed(3);
  }

  /* ---------- 02 · the two rules ---------- */
  var drs=[].slice.call(document.querySelectorAll("#duel .dr"));
  function act2(p){
    var head=document.querySelector("#duel .dh");
    if(head) head.style.setProperty("--ho", String(ease(seg(p,.08,.22))));
    drs.forEach(function(r,i){
      var s=i*0.13;
      r.style.setProperty("--o", String(ease(seg(p,.16+s,.40+s))));
    });
    var z=document.getElementById("dz");
    if(z) z.style.setProperty("--zo", String(ease(seg(p,.66,.86))));
  }

  /* ---------- 03 · ninety-one constellations ---------- */
  /* 10 external targets + 20 horizons + 16 country models + 36 feature sets
     + 9 stress tests. One field keeps the accent, the rest recede. */
  var TOTAL=91, SURVIVOR=57;                // a fixed field, so it never jumps
  var cells=[];
  (function(){
    var host=document.getElementById("cells"); if(!host) return;
    var frag=document.createDocumentFragment();
    for(var i=0;i<TOTAL;i++){
      var c=document.createElement("span");
      c.className="c"; c.appendChild(document.createElement("i"));
      frag.appendChild(c); cells.push(c);
    }
    host.appendChild(frag);
  })();
  function act3(p){
    var fade=ease(seg(p,.70,.90));
    cells.forEach(function(c,i){
      var s=(i/TOTAL)*0.42;
      var inn=ease(seg(p,.06+s,.24+s));
      var keep = i===SURVIVOR;
      var o = keep ? inn : lerp(inn, inn*0.14, fade);
      c.style.setProperty("--o", o.toFixed(3));
      c.style.setProperty("--a", keep ? (inn*fade).toFixed(3) : "0");
    });
  }

  /* ---------- 04 · C minus B ---------- */
  /* Two bars around a zero line. Wide viewports get one line per row
     (name left, figures right); narrow ones get their own viewBox with the
     name above and the figures below each bar, recomputed on resize. */
  var BARS=[
    { nm:"Logistic regression",  v:-0.019, lo:-0.042, hi: 0.001 },
    { nm:"Gradient boosting",    v:-0.064, lo:-0.114, hi:-0.015 }
  ];
  var CFG={
    wide:  { box:"0 0 1000 300", x0:60, x1:940, rows:[112,212], bh:30, cap:11,
             top:34, bot:276, split:false },
    narrow:{ box:"0 0 520 408",  x0:22, x1:498, rows:[110,278], bh:42, cap:16,
             top:28, bot:394, split:true }
  };
  /* The domain is cut to the data, so the two bars use the whole width
     instead of hanging in a corner. */
  var DOM_LO=-0.125, DOM_HI=0.012, CMODE="", GROUPS=[];

  function svgEl(n,a){
    var e=document.createElementNS("http://www.w3.org/2000/svg",n);
    for(var k in a) e.setAttribute(k,a[k]);
    return e;
  }
  function layoutC(){
    var svg=document.getElementById("cplot"); if(!svg) return;
    /* Narrow only in a portrait-shaped viewport; a landscape phone is wide
       and short, and the flat layout fits it far better. */
    var mode = (window.innerWidth<=1000 && window.innerHeight>=window.innerWidth)
      ? "narrow" : "wide";
    if(mode===CMODE) return;
    CMODE=mode;
    var c=CFG[mode];
    svg.setAttribute("viewBox", c.box);
    while(svg.firstChild) svg.removeChild(svg.firstChild);
    GROUPS=[];
    function X(v){ return c.x0 + (v-DOM_LO)/(DOM_HI-DOM_LO)*(c.x1-c.x0); }
    var zx=X(0);

    svg.appendChild(svgEl("line",{class:"zline",x1:zx,y1:c.top,x2:zx,y2:c.bot-26}));
    var zl=svgEl("text",{class:"zline-lab",x:(zx-8).toFixed(1),y:c.bot,"text-anchor":"end"});
    zl.textContent="0 · no contribution";
    zl.setAttribute("opacity","0"); svg.appendChild(zl);
    GROUPS.zero=zl;

    BARS.forEach(function(b,i){
      var y=c.rows[i];
      var g=svgEl("g",{});
      var x=X(b.v);
      g.appendChild(svgEl("rect",{class:"cbar",x:x.toFixed(1),y:(y-c.bh/2).toFixed(1),
        width:Math.max(1,zx-x).toFixed(1),height:c.bh,rx:2}));
      var lo=X(b.lo), hi=X(b.hi), ch=c.cap;
      g.appendChild(svgEl("path",{class:"ci",d:
        "M"+lo.toFixed(1)+" "+(y-ch)+"V"+(y+ch)+
        "M"+lo.toFixed(1)+" "+y+"H"+hi.toFixed(1)+
        "M"+hi.toFixed(1)+" "+(y-ch)+"V"+(y+ch)}));
      var nm=svgEl("text",{class:"lab nm",x:c.x0,y:(y-c.bh/2-(mode==="narrow"?20:14))});
      nm.textContent=b.nm;
      g.appendChild(nm);
      var vt=svgEl("text",{class:"lab"});
      vt.textContent = num(b.v,3)+"  ["+num(b.lo,3)+", "+num(b.hi,3)+"]";
      if(c.split){ vt.setAttribute("x",c.x0); vt.setAttribute("y", y+c.bh/2+36); }
      else { vt.setAttribute("x",(zx-12).toFixed(1)); vt.setAttribute("y", y-c.bh/2-14);
             vt.setAttribute("text-anchor","end"); }
      g.appendChild(vt);
      svg.appendChild(g);
      GROUPS.push(g);
    });
  }
  function act4(p){
    var svg=document.getElementById("cplot"); if(!svg) return;
    if(!GROUPS.length) layoutC();
    svg.style.setProperty("--z0", String(ease(seg(p,.06,.22))));
    if(GROUPS.zero) GROUPS.zero.setAttribute("opacity", String(ease(seg(p,.10,.26))));
    GROUPS.forEach(function(g,i){
      var s=i*0.18;
      g.style.setProperty("--l",  String(ease(seg(p,.18+s,.36+s))));
      g.style.setProperty("--g",  String(ease(seg(p,.24+s,.58+s))));
      g.style.setProperty("--ci", String(ease(seg(p,.52+s,.74+s))));
    });
  }

  /* ---------- one pass per frame ---------- */
  var TRACKS=[["c1",act1],["c2",act2],["c3",act3],["c4",act4]];
  var ticking=false;
  function frame(){
    ticking=false;
    TRACKS.forEach(function(t){
      var el=document.getElementById(t[0]); if(!el) return;
      var r=el.getBoundingClientRect();
      var travel=r.height-window.innerHeight;
      var p= travel<=0 ? 1 : clamp(-r.top/travel,0,1);
      var near = r.bottom>-200 && r.top<window.innerHeight+200;
      if(!near){
        if(el.dataset.settled==="1") return;
        el.dataset.settled="1"; t[1](p); return;
      }
      el.dataset.settled="0";
      t[1](p);
      var sc=el.querySelector(".scrub");
      if(sc) sc.style.setProperty("--p", p.toFixed(4));
    });
  }
  function onScroll(){ if(!ticking){ ticking=true; requestAnimationFrame(frame); } }
  function remeasure(){ layoutC(); onScroll(); }

  if(reduce){
    layoutC();
    TRACKS.forEach(function(t){ t[1](1); });
    var v=document.getElementById("mval"); if(v) v.textContent=VAL.toFixed(3);
  }else{
    window.addEventListener("scroll", onScroll, {passive:true});
    window.addEventListener("resize", remeasure);
    window.addEventListener("orientationchange", remeasure);
    window.addEventListener("load", remeasure);
    remeasure();
  }
})();
