/* Scroll-driven motion for the basics page.
   One rAF-throttled pass over the pinned tracks; every track maps its own
   scroll progress to CSS custom properties. Transform and opacity only. */
(function(){
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- helpers ---------- */
  function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
  function seg(x,a,b){ return clamp((x-a)/(b-a),0,1); }      // progress inside a window
  function ease(t){ return t*t*(3-2*t); }                     // smoothstep: settles heavily
  function lerp(a,b,t){ return a+(b-a)*t; }

  /* ---------- entrance reveals ---------- */
  var io = new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add("in");
      io.unobserve(e.target); } });
  },{threshold:.25, rootMargin:"0px 0px -8% 0px"});
  document.querySelectorAll(".rv,.lines").forEach(function(el){ io.observe(el); });

  /* ---------- chapter rail ---------- */
  var STEPS=["00","01","02","03","04","05"];
  document.querySelectorAll(".rail").forEach(function(rail){
    var mine=parseInt(rail.dataset.rail,10);
    rail.innerHTML = STEPS.map(function(s,i){
      var cls = i===mine ? "on" : (i<mine ? "done" : "");
      return '<span class="'+cls+'">'+s+'</span>';
    }).join("");
  });

  /* ---------- 00 · article to row ---------- */
  var pipeSteps=[].slice.call(document.querySelectorAll("#pipe .step"));
  var pipeArrows=[].slice.call(document.querySelectorAll("#pipe .arrow"));
  function act0(p){
    pipeSteps.forEach(function(s,i){
      s.style.setProperty("--o", String(ease(seg(p,.10+i*.16,.34+i*.16))));
    });
    pipeArrows.forEach(function(a,i){
      a.style.setProperty("--ao", String(ease(seg(p,.24+i*.16,.38+i*.16))));
    });
  }

  /* ---------- 01 · the record ---------- */
  // The real 61 fields of the export; empty ones are shown as a middle dot.
  var RAW = ["1223954814","20250201","202502","2025","2025.0849","REB","REBEL","","","","",
    "","REB","","","COD","GOMA","COD","","","","","","","","1","192","192","19","4",
    "-9.5","63","9","63","-5.6848718","1","Germany","GM","GM00","","51.5","10.5","-1968741",
    "4","Goma, Nord-Kivu","CG","CG08","","-1.67917","29.2228","-3414067",
    "1","Germany","GM","GM00","","51.5","10.5","-1968741","20250201000000","npr.org/..."];
  var KEEP = {26:1,28:1,29:1,30:1,31:1,32:1,33:1,34:1,36:1,37:1};
  (function(){
    var host=document.getElementById("rawline"); if(!host) return;
    host.innerHTML = RAW.map(function(v,i){
      var t = v==="" ? "·" : (v.length>22 ? v.slice(0,20)+"…" : v);
      return (KEEP[i] ? "<em>"+t+"</em>" : t);
    }).join("&nbsp;&nbsp;");
  })();

  var grps = [].slice.call(document.querySelectorAll("#grps .grp"));
  var HOME=[];
  function measureGroups(){
    var box=document.getElementById("grps"); if(!box) return;
    grps.forEach(function(g){ g.style.setProperty("--x","0px"); g.style.setProperty("--y","0px");
      g.style.setProperty("--s","1"); });
    var b=box.getBoundingClientRect();
    var cx=b.left+b.width/2, cy=b.top+b.height/2;
    HOME=grps.map(function(g){
      var r=g.getBoundingClientRect();
      return { dx: cx-(r.left+r.width/2), dy: cy-(r.top+r.height/2) };
    });
  }
  function act1(p){
    if(!HOME.length) measureGroups();
    var raw=document.getElementById("rawline");
    if(raw){
      raw.style.setProperty("--rawOp", String(1-ease(seg(p,.16,.30))));
      raw.style.setProperty("--rawScale", String(lerp(.96,1.06,ease(seg(p,0,.30)))));
    }
    var dim = ease(seg(p,.46,.68));          // the unused fields recede
    grps.forEach(function(g,i){
      var home=HOME[i]||{dx:0,dy:0};
      var st=i*0.014;
      var out=ease(seg(p,.20+st,.40+st));    // 0 = on one spot, 1 = in its place
      var keep=g.classList.contains("keep");
      var back=keep?0:dim;
      g.style.setProperty("--x",(home.dx*(1-out)).toFixed(1)+"px");
      g.style.setProperty("--y",(home.dy*(1-out)).toFixed(1)+"px");
      g.style.setProperty("--s",(lerp(.6,1,out)*lerp(1,.94,back)).toFixed(3));
      g.style.setProperty("--o",(out*lerp(1,.16,back)).toFixed(3));
    });
  }

  /* ---------- 02 · the swarm ---------- */
  var dots=[], SWARM={w:0,h:0};
  (function(){
    var host=document.getElementById("swarm"); if(!host) return;
    var N = window.innerWidth<1000 ? 110 : 190;
    var frag=document.createDocumentFragment();
    for(var i=0;i<N;i++){
      var d=document.createElement("span");
      d.className="dot"+(i%9===0?" big":"")+(i%23===0?" acc":"");
      // deterministic sunflower scatter, so the picture never jumps between visits
      var a=(i*2.399963), r=Math.sqrt((i+1)/N);
      dots.push({el:d, x:50+Math.cos(a)*r*44, y:50+Math.sin(a)*r*42, t:i/N});
      frag.appendChild(d);
    }
    host.appendChild(frag);
    dots.forEach(function(d){ d.el.style.left=d.x+"%"; d.el.style.top=d.y+"%"; });
  })();
  function measureSwarm(){
    var host=document.getElementById("swarm");
    if(host){ var r=host.getBoundingClientRect(); SWARM.w=r.width; SWARM.h=r.height; }
  }
  function act2(p){
    if(!SWARM.w) measureSwarm();
    dots.forEach(function(d){
      var g = ease(seg(p, .12 + d.t*0.26, .58 + d.t*0.26));
      var dx = (50-d.x)/100 * SWARM.w * g * 0.62;   // squeeze inwards
      var dy = (50-d.y)/100 * SWARM.h * g;          // flatten onto the centre line
      d.el.style.transform = "translate3d("+dx.toFixed(1)+"px,"+dy.toFixed(1)+"px,0) scale("+
        lerp(1,.45,g).toFixed(3)+")";
      d.el.style.opacity = String(lerp(.6,0,ease(seg(p,.50,.70))));
    });
    var out=document.querySelector("#t2 .rowout");
    if(out) out.style.setProperty("--rowOp", String(ease(seg(p,.54,.78))));
    var cnt=document.getElementById("cnt");
    if(cnt){
      var v = Math.round(lerp(6237331, 730, ease(seg(p,.14,.76))));
      cnt.textContent = v.toLocaleString("en-US");
      var unit=document.getElementById("unit");
      if(unit){
        var wanted = v>10000 ? "events after filtering" : "rows · one per country and day";
        if(unit.textContent!==wanted) unit.textContent=wanted;
      }
    }
  }

  /* ---------- 03 · the seven features ---------- */
  var fs=[].slice.call(document.querySelectorAll("#feat .f"));
  function act3(p){
    fs.forEach(function(f,i){
      var s=i*0.05;
      f.style.setProperty("--fo", String(ease(seg(p,.14+s,.40+s))));
    });
  }

  /* ---------- 04 · the z-score ---------- */
  // z mapped to the plot: y(z) = 295 - z*65, so +1.5 sigma lands on 197.5
  var SER=(function(){
    var pts=[], n=64;
    for(var i=0;i<n;i++){
      var x=30 + (700*i/(n-1));
      var z = Math.sin(i*0.55)*0.28 + Math.sin(i*0.19+1.2)*0.20 + Math.cos(i*0.9)*0.09;
      if(i>44) z += Math.pow((i-44)/(n-1-44), 1.7) * 2.15;
      pts.push([x, 295 - z*65, z]);
    }
    return pts;
  })();
  (function(){
    var path=document.getElementById("ser"); if(!path) return;
    path.setAttribute("d","M"+SER.map(function(q){
      return q[0].toFixed(1)+" "+q[1].toFixed(1); }).join("L"));
    var len=path.getTotalLength ? path.getTotalLength() : 2000;
    path.style.setProperty("--len", String(Math.ceil(len)));
    var cross=null;
    for(var i=0;i<SER.length;i++){ if(SER[i][2]>=1.5){ cross=SER[i]; break; } }
    if(!cross) cross=SER[SER.length-1];
    var hit=document.getElementById("hit");
    hit.setAttribute("cx",cross[0].toFixed(1)); hit.setAttribute("cy",cross[1].toFixed(1));
  })();
  function act4(p){
    var plot=document.getElementById("plot"); if(!plot) return;
    plot.style.setProperty("--bandOp", String(ease(seg(p,.10,.30))));
    plot.style.setProperty("--draw",   String(ease(seg(p,.16,.62))));
    plot.style.setProperty("--thrOp",  String(ease(seg(p,.50,.66))));
    var lab=document.getElementById("thrlab");
    if(lab) lab.setAttribute("opacity", String(ease(seg(p,.54,.70))));
    plot.style.setProperty("--hitOp", String(ease(seg(p,.66,.78))));
    plot.style.setProperty("--hitS",  String(lerp(.2,1,ease(seg(p,.66,.84)))));
  }

  /* ---------- 05 · the line ---------- */
  function act5(p){
    var g=document.querySelector("#t5 .gline"); if(!g) return;
    g.style.setProperty("--gp", String(ease(seg(p,.14,.60))));
    var de=document.getElementById("mDE"), us=document.getElementById("mUS");
    if(de) de.style.setProperty("--mo", String(ease(seg(p,.26,.42))));
    if(us) us.style.setProperty("--mo", String(ease(seg(p,.48,.64))));
  }

  /* ---------- one pass per frame ---------- */
  var TRACKS=[["t0",act0],["t1",act1],["t2",act2],["t3",act3],["t4",act4],["t5",act5]];
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
  var ticking=false;
  function onScroll(){ if(!ticking){ ticking=true; requestAnimationFrame(frame); } }
  function remeasure(){ measureGroups(); measureSwarm(); onScroll(); }

  if(reduce){
    TRACKS.forEach(function(t){ t[1](1); });
    document.querySelectorAll(".rv,.lines").forEach(function(el){ el.classList.add("in"); });
    var c=document.getElementById("cnt"); if(c) c.textContent="730";
    var u=document.getElementById("unit");
    if(u) u.textContent="rows · one per country and day";
  }else{
    window.addEventListener("scroll", onScroll, {passive:true});
    window.addEventListener("resize", remeasure);
    window.addEventListener("load", remeasure);
    remeasure();
  }
})();
