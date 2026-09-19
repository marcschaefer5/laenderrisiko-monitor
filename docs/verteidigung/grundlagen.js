/* Scroll-driven motion for the basics page.
   One rAF-throttled pass over the pinned tracks; every track maps its own
   scroll progress to CSS custom properties. Transform and opacity only. */
(function(){
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- helpers ---------- */
  function clamp(v,a,b){ return v<a?a:(v>b?b:v); }
  // progress of x inside [a,b], clamped
  function seg(x,a,b){ return clamp((x-a)/(b-a),0,1); }
  // smoothstep — gives the heavy, settling feel of the reference motion
  function ease(t){ return t*t*(3-2*t); }
  function lerp(a,b,t){ return a+(b-a)*t; }

  /* ---------- entrance reveals ---------- */
  var io = new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add("in");
      io.unobserve(e.target); } });
  },{threshold:.25, rootMargin:"0px 0px -8% 0px"});
  document.querySelectorAll(".rv,.lines").forEach(function(el){ io.observe(el); });

  /* ---------- ACT 1 · the raw line ---------- */
  // 61 tab-separated fields; the ones the thesis uses are marked.
  var RAW = ["1223954814","20250201","202502","2025","2025.0849","REB","REBEL","","","","",
    "","REB","","","COD","GOMA","COD","","","","","","","","1","192","192","19","4",
    "-9.5","63","9","63","-5.6848718","1","Germany","GM","GM00","","51.5","10.5","-1968741",
    "4","Goma, Nord-Kivu, Congo","CG","CG08","","-1.67917","29.2228","-3414067",
    "1","Germany","GM","GM00","","51.5","10.5","-1968741","20250201000000",
    "https://www.npr.org/2025/01/31/nx-s1-5281422/congo-goma-fighting-m23-rwanda-drc"];
  var KEEP = {26:1,28:1,29:1,30:1,31:1,32:1,33:1,34:1,36:1,37:1};
  (function(){
    var host=document.getElementById("rawline"); if(!host) return;
    var html="";
    for(var i=0;i<RAW.length;i++){
      var v=RAW[i]===""? "·" : RAW[i];
      if(v.length>34) v=v.slice(0,31)+"…";
      html += (KEEP[i]? "<em>"+v+"</em>" : v) + (i<RAW.length-1 ? "<span class='sep'>\t</span>" : "");
    }
    host.innerHTML=html;
  })();

  var grps = [].slice.call(document.querySelectorAll("#grps .grp"));
  var KEPT = grps.filter(function(g){ return g.classList.contains("keep"); });

  // Each group's offset back to the centre of the field block. The disassembly
  // runs this in reverse: everything starts on one spot and moves out to its place.
  var HOME=[];
  function measureGroups(){
    var box=document.getElementById("grps"); if(!box) return;
    // neutralise transforms before measuring, otherwise we measure our own animation
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

    // 0.00–0.16  the raw line holds, pushed slightly toward the viewer
    // 0.16–0.34  it dissolves and the eight field groups move out from one point
    // 0.34–0.92  one group at a time takes focus and explains itself
    if(raw){
      raw.style.setProperty("--rawOp", String(1-ease(seg(p,.14,.28))));
      raw.style.setProperty("--rawScale", String(lerp(.95,1.08,ease(seg(p,0,.28)))));
    }

    var dim = ease(seg(p,.36,.56));
    // which kept group is in focus: a slow pass from .38 to .92
    var pass = seg(p,.38,.92) * KEPT.length;
    var idx  = clamp(Math.floor(pass), 0, KEPT.length-1);

    grps.forEach(function(g,i){
      var home=HOME[i]||{dx:0,dy:0};
      var st=i*0.012;
      var out=ease(seg(p,.16+st,.32+st));          // 0 = on the centre spot, 1 = in place
      var keep=g.classList.contains("keep");
      var back=keep?0:dim;                          // unused fields recede
      g.style.setProperty("--x",(home.dx*(1-out)).toFixed(1)+"px");
      g.style.setProperty("--y",(home.dy*(1-out)).toFixed(1)+"px");
      g.style.setProperty("--s",(lerp(.55,1,out)*lerp(1,.94,back)).toFixed(3));
      g.style.setProperty("--o",(out*lerp(1,.18,back)).toFixed(3));
      var focused = keep && p>.38 && KEPT[idx]===g;
      g.classList.toggle("showd", focused);
      g.classList.toggle("focus", focused);
    });
  }

  /* ---------- ACT 2 · the swarm ---------- */
  var dots=[];
  (function(){
    var host=document.getElementById("swarm"); if(!host) return;
    var N = window.innerWidth<700 ? 90 : 170;
    var frag=document.createDocumentFragment();
    for(var i=0;i<N;i++){
      var d=document.createElement("span");
      d.className="dot"+(i%9===0?" big":"")+(i%23===0?" acc":"");
      // deterministic scatter, so the picture is the same on every visit
      var a=(i*2.399963), r=Math.sqrt((i+1)/N);
      dots.push({el:d, x:50+Math.cos(a)*r*46, y:50+Math.sin(a)*r*44, t:i/N});
      frag.appendChild(d);
    }
    host.appendChild(frag);
    dots.forEach(function(d){ d.el.style.left=d.x+"%"; d.el.style.top=d.y+"%"; });
  })();

  var SWARM={w:0,h:0};
  function measure(){
    measureGroups();
    var host=document.getElementById("swarm");
    if(host){ var r=host.getBoundingClientRect(); SWARM.w=r.width; SWARM.h=r.height; }
  }
  measure();

  function act2(p){
    if(!SWARM.w) measure();
    dots.forEach(function(d,i){
      var st = seg(p, .12 + d.t*0.26, .58 + d.t*0.26);
      var g = ease(st);
      // horizontal compression, full vertical flattening: the cloud becomes a line
      var dx = (50-d.x)/100 * SWARM.w * g * 0.62;
      var dy = (50-d.y)/100 * SWARM.h * g;
      d.el.style.transform = "translate3d("+dx.toFixed(1)+"px,"+dy.toFixed(1)+"px,0) scale("+lerp(1,.45,g).toFixed(3)+")";
      d.el.style.opacity = String(lerp(.62,0,ease(seg(p,.52,.72))));
    });
    var card=document.querySelector("#t2 .rowcard");
    if(card) card.style.setProperty("--rowOp", String(ease(seg(p,.56,.80))));
    var cnt=document.getElementById("cnt");
    if(cnt){
      var k = ease(seg(p,.14,.78));
      var v = Math.round(lerp(6237331, 730, k));
      cnt.textContent = v.toLocaleString("en-US");
      var unit=document.getElementById("unit");
      if(unit){
        var wanted = v>10000 ? "events after filtering"
                             : "rows \u00b7 365 days \u00d7 2 countries";
        if(unit.textContent!==wanted) unit.textContent=wanted;
      }
    }
  }

  /* ---------- ACT 3 · features ---------- */
  var fs=[].slice.call(document.querySelectorAll("#feat .f"));
  function act3(p){
    fs.forEach(function(f,i){
      var s=i*0.055;
      f.style.setProperty("--fo", String(ease(seg(p,.14+s,.42+s))));
    });
  }

  /* ---------- ACT 4 · the z-score ---------- */
  // z-units mapped to the plot: y(z) = 255 - z*55, so +1.5 sigma sits at 172.5
  var SER = (function(){
    var pts=[], n=64;
    for(var i=0;i<n;i++){
      var x=60 + (820*i/(n-1));
      var z = Math.sin(i*0.55)*0.28 + Math.sin(i*0.19+1.2)*0.20 + Math.cos(i*0.9)*0.09;
      if(i>44) z += Math.pow((i-44)/(n-1-44), 1.7) * 2.15;   // the build
      pts.push([x, 255 - z*55, z]);
    }
    return pts;
  })();
  (function(){
    var path=document.getElementById("ser"); if(!path) return;
    var d="M"+SER.map(function(p){return p[0].toFixed(1)+" "+p[1].toFixed(1);}).join("L");
    path.setAttribute("d",d);
    var len=path.getTotalLength ? path.getTotalLength() : 2200;
    path.style.setProperty("--len", String(Math.ceil(len)));
    var hit=document.getElementById("hit");
    var cross=null;
    for(var i=0;i<SER.length;i++){ if(SER[i][2]>=1.5){ cross=SER[i]; break; } }
    if(!cross) cross=SER[SER.length-1];
    hit.setAttribute("cx",cross[0].toFixed(1)); hit.setAttribute("cy",cross[1].toFixed(1));
  })();
  function act4(p){
    var plot=document.getElementById("plot"); if(!plot) return;
    plot.style.setProperty("--draw", String(ease(seg(p,.10,.58))));
    plot.style.setProperty("--bandOp", String(ease(seg(p,.22,.46))));
    plot.style.setProperty("--thrOp", String(ease(seg(p,.46,.62))));
    var lab=document.getElementById("thrlab");
    if(lab) lab.setAttribute("opacity", String(ease(seg(p,.50,.66))));
    plot.style.setProperty("--hitOp", String(ease(seg(p,.62,.74))));
    plot.style.setProperty("--hitS", String(lerp(.2,1,ease(seg(p,.62,.80)))));
  }

  /* ---------- ACT 5 · the threshold ---------- */
  function act5(p){
    var g=document.querySelector("#t5 .gline"); if(!g) return;
    g.style.setProperty("--gp", String(ease(seg(p,.18,.62))));
    var de=document.getElementById("mDE"), us=document.getElementById("mUS");
    if(de) de.style.setProperty("--mo", String(ease(seg(p,.34,.50))));
    if(us) us.style.setProperty("--mo", String(ease(seg(p,.54,.70))));
  }

  /* ---------- the single scroll pass ---------- */
  var TRACKS=[["t1",act1],["t2",act2],["t3",act3],["t4",act4],["t5",act5]];
  function frame(){
    ticking=false;
    TRACKS.forEach(function(t){
      var el=document.getElementById(t[0]); if(!el) return;
      var r=el.getBoundingClientRect();
      var travel=r.height-window.innerHeight;
      var p= travel<=0 ? 1 : clamp(-r.top/travel,0,1);
      // only work while the track is anywhere near the viewport
      if(r.bottom<-200 || r.top>window.innerHeight+200){
        if(el.dataset.settled==="1") return;
        el.dataset.settled="1"; t[1](p); return;
      }
      el.dataset.settled="0";
      t[1](p);
      var sc=el.querySelector(".scrub i");
      if(sc) sc.parentNode.style.setProperty("--p", p.toFixed(4));
    });
  }
  var ticking=false;
  function onScroll(){ if(!ticking){ ticking=true; requestAnimationFrame(frame); } }

  window.addEventListener("load", function(){ measure(); frame(); });

  if(reduce){
    // no scrubbing: everything is shown in its finished state
    TRACKS.forEach(function(t){ t[1](1); });
    document.querySelectorAll(".rv,.lines").forEach(function(el){ el.classList.add("in"); });
    var c=document.getElementById("cnt"); if(c) c.textContent="730";
  }else{
    window.addEventListener("scroll", onScroll, {passive:true});
    window.addEventListener("resize", function(){ measure(); onScroll(); });
    frame();
  }
})();
