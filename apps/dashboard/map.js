// Local interactive geographic view. No coordinates, tiles or hazard layers are inferred.
export function createMap({locations,records,gaps=[],openRecord,lang='en'}) {
  const words=lang==='my'?{layer:'မြေပုံအလွှာ',severity:'ပြင်းထန်မှု',confidence:'အထောက်အထား',freshness:'အချက်အလက်သက်တမ်း',investigation:'စုံစမ်းရန်',assistance:'ထောက်ပံ့မှု',zoomIn:'ချဲ့ရန်',zoomOut:'ချုံ့ရန်',reset:'မူလမြင်ကွင်း',select:'ဒေသရွေးရန်',unknown:'မသိရသေး',open:'မှတ်တမ်းကြည့်ရန်'}:{layer:'Map layer',severity:'Severity',confidence:'Evidence confidence',freshness:'Freshness',investigation:'Unreported / investigation',assistance:'Confirmed assistance gap',zoomIn:'Zoom in',zoomOut:'Zoom out',reset:'Fit all',select:'Select a village marker or cluster',unknown:'Unknown',open:'Open record'};
  const make=(tag,text,attributes={})=>{const n=document.createElement(tag);if(text)n.textContent=text;for(const [k,v]of Object.entries(attributes))n.setAttribute(k,v);return n;};
  const byLocation=new Map(records.map(r=>[r.location_id,r]));
  const points=locations.filter(l=>l.coordinate_status==='reviewer_verified'&&Number.isFinite(l.latitude)&&Number.isFinite(l.longitude)&&Math.abs(l.latitude)<85.0511).map(l=>({...l,report:byLocation.get(l.id),x:l.longitude,y:Math.log(Math.tan(Math.PI/4+l.latitude*Math.PI/360))*180/Math.PI}));
  const root=make('div',null,{class:'interactive-map'});
  const controls=make('div',null,{class:'split map-controls'});
  const select=make('select',null,{'aria-label':words.layer});
  for(const key of ['severity','confidence','freshness','investigation','assistance'])select.append(make('option',words[key],{value:key}));
  controls.append(select);
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 900 450');svg.setAttribute('role','group');svg.setAttribute('aria-label','Geographic map of reviewer-approved coordinates');svg.setAttribute('tabindex','0');svg.classList.add('map-canvas');
  const detail=make('div',words.select,{class:'map-detail','aria-live':'polite'});
  const minX=Math.min(...points.map(p=>p.x)),maxX=Math.max(...points.map(p=>p.x)),minY=Math.min(...points.map(p=>p.y)),maxY=Math.max(...points.map(p=>p.y));
  const fit={x:(minX+maxX)/2,y:(minY+maxY)/2,scale:Math.min(760/Math.max(.025,maxX-minX),330/Math.max(.025,maxY-minY))};
  let view={...fit};
  function action(text,fn){const b=make('button',text,{class:'btn'});b.addEventListener('click',fn);controls.append(b);return b;}
  action(words.zoomIn,()=>zoom(1.5));action(words.zoomOut,()=>zoom(1/1.5));action(words.reset,()=>{view={...fit};draw();});
  for(const [label,x,y]of [['←',-1,0],['→',1,0],['↑',0,1],['↓',0,-1]])action(label,()=>{view.x+=x*100/view.scale;view.y+=y*100/view.scale;draw();});
  function zoom(factor){view.scale=Math.max(fit.scale/2,Math.min(fit.scale*4096,view.scale*factor));draw();}
  function project(p){return {x:450+(p.x-view.x)*view.scale,y:225-(p.y-view.y)*view.scale};}
  function color(p){const r=p.report;
    if(select.value==='confidence')return r?.status==='verified'?'#205948':r?'#a76e26':'#75817b';
    if(select.value==='investigation')return !r||r.investigation_reasons?.length?'#a76e26':'#205948';
    if(select.value==='freshness'){const values=Object.values(r?.freshness||{}).map(f=>f.freshness).filter(f=>f!==null);if(!values.length)return '#75817b';return `hsl(${Math.min(...values)*120} 45% 35%)`;}
    if(select.value==='assistance'){const needs=gaps.filter(g=>g.location_id===p.id);if(!needs.length||needs.some(g=>g.confirmed_gap===null))return '#75817b';return needs.some(g=>g.confirmed_gap>0)?'#a76e26':'#205948';}
    if(!r||r.severity?.status!=='complete_indicator')return '#75817b';return `hsl(${120-r.severity.lower*1.2} 45% 35%)`;
  }
  function show(group){detail.replaceChildren();for(const p of group){const r=p.report;const title=make('strong',p.village+' · '+p.township);detail.append(title,make('p',p.latitude.toFixed(5)+', '+p.longitude.toFixed(5)+' · '+p.coordinate_source));
      detail.append(make('p',r?'Evidence: '+r.status+' · Severity: '+(r.severity?.lower===null?words.unknown:r.severity.lower+'–'+r.severity.upper)+' · Observed: '+(r.data.observed_at||words.unknown):'No report in this filter. Needs investigation; severity unknown.'));
      if(r){detail.append(make('p','Freshness by field: '+Object.entries(r.freshness||{}).map(([key,f])=>key+' '+(f.age_hours===null?words.unknown:f.age_hours+' h; '+f.status)).join(' · ')));const b=make('button',words.open,{class:'btn'});b.addEventListener('click',()=>openRecord(r.id));detail.append(b);} }
  }
  function node(tag,attributes,text){const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attributes))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
  function draw(){svg.replaceChildren();
    const gridStep=Math.pow(10,Math.floor(Math.log10(100/view.scale)));
    for(let lng=Math.floor((view.x-450/view.scale)/gridStep)*gridStep;lng<view.x+450/view.scale;lng+=gridStep){const x=project({x:lng,y:0}).x;svg.append(node('line',{x1:x,x2:x,y1:0,y2:450,class:'geo-grid'}),node('text',{x:x+3,y:445,class:'geo-label'},lng.toFixed(3)+'° E'));}
    const buckets=new Map();for(const p of points){const screen=project(p);if(screen.x<-40||screen.x>940||screen.y<-40||screen.y>490)continue;const key=Math.floor(screen.x/35)+':'+Math.floor(screen.y/35);if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push({...p,screen});}
    for(const group of buckets.values()){const x=group.reduce((a,p)=>a+p.screen.x,0)/group.length,y=group.reduce((a,p)=>a+p.screen.y,0)/group.length;const n=node('g',{tabindex:0,role:'button','aria-label':group.map(p=>p.village).join(', ')});n.append(node('circle',{cx:x,cy:y,r:group.length>1?15:8,fill:group.length>1?'#233d32':color(group[0]),class:'map-pin'}));if(group.length>1)n.append(node('text',{x,y:y+4,'text-anchor':'middle',fill:'#fff','font-size':12,'pointer-events':'none'},String(group.length)));n.append(node('title',{},group.map(p=>p.village).join(', ')));const choose=()=>{show(group);if(group.length>1){view.x=group.reduce((a,p)=>a+p.x,0)/group.length;view.y=group.reduce((a,p)=>a+p.y,0)/group.length;zoom(2);}};n.addEventListener('click',choose);n.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose();}});svg.append(n);}
  }
  select.addEventListener('change',draw);
  svg.addEventListener('keydown',e=>{if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();if(e.key==='+'||e.key==='=')zoom(1.5);else if(e.key==='-')zoom(1/1.5);else{view.x+=(e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0)*100/view.scale;view.y+=(e.key==='ArrowUp'?1:e.key==='ArrowDown'?-1:0)*100/view.scale;draw();}}});
  let drag=null;svg.addEventListener('pointerdown',e=>{if(e.target===svg||e.target.tagName==='line'){drag={x:e.clientX,y:e.clientY,cx:view.x,cy:view.y};svg.setPointerCapture(e.pointerId);}});svg.addEventListener('pointermove',e=>{if(drag){const ratio=900/svg.getBoundingClientRect().width;view.x=drag.cx-(e.clientX-drag.x)*ratio/view.scale;view.y=drag.cy+(e.clientY-drag.y)*ratio/view.scale;draw();}});svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointercancel',()=>drag=null);
  root.append(controls,svg,make('p','Projection: Web Mercator · Longitude/latitude from reviewer-approved sources. Gray = unknown; amber = needs review or confirmed unmet gap. Severity, evidence and freshness are separate layers. No basemap, boundaries or hazard evidence is supplied.',{class:'muted'}),detail);
  draw();return root;
}
