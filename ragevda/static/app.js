// RAG-EVDA app JS (split from webapp INDEX_HTML).
// ---- enterprise theme toggle (fixed dark/light rendering) ----
const themeBtn = document.getElementById('themeBtn');
const metaTheme = document.getElementById('metaTheme');
function applyTheme(t, animate){
  if(animate){ document.body.classList.add('theme-anim'); setTimeout(()=>document.body.classList.remove('theme-anim'), 450); }
  const light = (t==='light');
  document.body.classList.toggle('light', light);
  document.body.setAttribute('data-theme', light ? 'light' : 'dark');
  document.documentElement.style.colorScheme = light ? 'light' : 'dark';
  if(metaTheme) metaTheme.setAttribute('content', light ? '#F3EDF7' : '#141218');
  themeBtn.textContent = light ? ' Light' : ' Dark';
}
let savedTheme = null;
try{ savedTheme = localStorage.getItem('ragevda-theme'); }catch(e){}
if(!savedTheme && window.matchMedia){ savedTheme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; }
applyTheme(savedTheme||'dark', false);
themeBtn.onclick = () => {
  const next = (document.body.classList.contains('light') || document.body.getAttribute('data-theme')==='light') ? 'dark':'light';
  try{ localStorage.setItem('ragevda-theme', next); }catch(e){}
  applyTheme(next, true); toast(next==='light' ? 'Light mode — Material 3 light tokens applied.' : 'Dark mode — Material 3 dark tokens applied.');
};
function toast(msg, kind){
  const box=document.getElementById('toasts'); if(!box) return;
  const el=document.createElement('div'); el.className='toast'+(kind==='ok'?' ok':kind==='bad'?' bad':''); el.innerHTML=msg;
  box.appendChild(el); setTimeout(()=>{ el.style.opacity='0'; setTimeout(()=>el.remove(),400); }, 4200);
}
// ---- fluid stepper navigation ----
let lastJob=null;
function goStep(which){
  const inputs=document.getElementById('page-inputs'), feats=document.getElementById('page-features'), outs=document.getElementById('page-outputs');
  inputs.classList.remove('active'); feats.classList.remove('active'); outs.classList.remove('active');
  setStep('step1',''); setStep('step2',''); setStep('step3','');
  if(which==='inputs'){ inputs.classList.add('active'); setStep('step1','active'); }
  else if(which==='features'){
    if(!lastJob){ toast('Run an audit first — analysis appears here.'); inputs.classList.add('active'); setStep('step1','active'); return; }
    feats.classList.add('active'); setStep('step1','done'); setStep('step2','active'); loadFeatures(lastJob, true);
  } else {
    if(!lastJob){ toast('Run an audit first — outputs appear here.'); inputs.classList.add('active'); setStep('step1','active'); return; }
    outs.classList.add('active'); setStep('step1','done'); setStep('step2','done'); setStep('step3','active'); loadOutputs(lastJob, true);
  }
  window.scrollTo({top:0, behavior:'smooth'});
}

const adv = document.getElementById('advToggle');
adv.onclick = () => {
  const p = document.getElementById('advPanel');
  const hidden = p.style.display === 'none';
  p.style.display = hidden ? 'block' : 'none';
  adv.textContent = (hidden ? '' : '') + ' Enterprise inputs 6–11 + engine tuning (auto-filled — review & expand)';
};

function splitList(s){ return s.split(/[\n,]/).map(x=>x.trim()).filter(Boolean); }

// ---- Auto-Detect: fetch the submitted URL/brand and fill ALL fields ----
const probeBtn=document.getElementById('probeBtn');
const probeStatus=document.getElementById('probeStatus');
function setProbeStatus(html, ok){
  probeStatus.innerHTML=html;
  probeStatus.style.display='block';
  probeStatus.style.color = ok ? 'var(--m3-tertiary)' : 'var(--m3-error)';
}
function fillField(name, value){
  const el=document.querySelector('[name="'+name+'"]');
  if(!el) return false;
  const type=(el.getAttribute('type')||'text').toLowerCase();
  const tag=el.tagName.toUpperCase();
  if(type==='checkbox'){
    if(value){ el.checked=true; }
  } else if(tag==='SELECT'){
    if([].slice.call(el.options).some(o=>o.value===String(value))){ el.value=String(value); }
  } else if(type==='number'){
    if(value!=null && value!==''){ el.value=String(value); }
  } else {
    el.value = value==null ? '' : String(value);
  }
  // open the advanced panel whenever an advanced-only field gets filled
  const core=['target_brand','industry_topics','competitor_entities','crawl_depth','locality'];
  if(core.indexOf(name)<0){
    const p=document.getElementById('advPanel');
    if(p && p.style.display==='none'){
      p.style.display='block';
      document.getElementById('advToggle').textContent=' Enterprise inputs 6–11 + engine tuning (auto-filled — review & expand)';
    }
  }
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
}
async function runProbe(){
  const input=document.querySelector('[name="target_brand"]').value.trim();
  if(!input){ setProbeStatus('Enter a brand or URL first.', false); return; }
  probeBtn.disabled=true; probeBtn.textContent='⏳ Deep-researching…';
  setProbeStatus(' <b>Stage 1/4</b> fetching live homepage + robots / sitemap / about / products…', true);
  const stages=document.getElementById('probeStages'); stages.style.display='block';
  stages.innerHTML='<div class="skel" style="height:14px; margin:4px 0"></div><div class="skel" style="height:14px; margin:4px 0"></div>';
  const stageTimer=setInterval(()=>{ stages.innerHTML+=''; }, 1000);
  try{
    const resp=await fetch('/api/probe',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:input})});
    const d=await resp.json();
    clearInterval(stageTimer); stages.style.display='none';
    if(d.error){ setProbeStatus('Detect failed: '+d.error, false); probeBtn.disabled=false; probeBtn.textContent='Auto-Detect Deep Research'; return; }
    // Fill EVERY returned field that has a matching form element.
    const known=['target_brand','industry_topics','competitor_entities','crawl_depth',
      'locality','harvester','prefer_searxng','searxng_base_url','auto_threshold',
      'high_relevance_threshold','search_intent','spacy_model','embedding_model',
      'engine_matrix','entity_weighting','ontology_aliases','query_templates',
      'serp_footprints','content_feeds','corpus_files','corpus_dir','chunk_tokens',
      'chunk_overlap_tokens','target_entity_density','top_k_retrieval',
      'synthetic_query_count','ollama_base_url','ollama_model'];
    let filled=[], skipped=[];
    for(const key of Object.keys(d)){
      if(key.indexOf('_')===0) continue;
      if(known.indexOf(key)<0) continue;
      if(fillField(key, d[key])) filled.push(key); else skipped.push(key);
    }
    const detested = {brand:d.target_brand,
      topics:(d.industry_topics||'').split('\n').filter(Boolean).length,
      comps:(d.competitor_entities||'').split('\n').filter(Boolean).length,
      locality:d.locality||'auto'};
    try{
      document.getElementById('hsTopics').textContent=detested.topics||'—';
      document.getElementById('hsComps').textContent=detested.comps||'—';
      document.getElementById('hsDepth').textContent=d.crawl_depth||'—';
      document.getElementById('hsLocality').textContent=detested.locality||'—';
    }catch(e){}
    const badge=document.getElementById('fb-brand'); if(badge) badge.classList.add('show');
    let note='';
    if(d._meta){ const m=d._meta; note=' — source: '+(m.title||m.domain||'web')+' · '+(m.note||''); }
    if(d._meta && d._meta.fields_filled){ note+=' · verified fields: '+d._meta.fields_filled.length; }
    const missing = ['corpus_dir','corpus_files'].filter(k=>{
      const el=document.querySelector('[name="'+k+'"]'); return el && (!el.value||!el.value.trim());
    });
    let msg=' <b>Deep research complete.</b> Brand "'+detested.brand+'" with '+detested.topics+' live topics &amp; '+
      detested.comps+' verified competitors (locality '+detested.locality+'). <b>'+filled.length+'/'+known.length+' enterprise fields auto-filled</b> from real-time evidence.'+note;
    if(missing.length) msg+=' · <b>Add manually:</b> '+missing.join(', ')+' (internal paths only — undetectable from the web)';
    setProbeStatus(msg, true);
    toast(' Deep research filled '+filled.length+' fields with verified live data.', 'ok');
  }catch(err){ setProbeStatus('Detect error: '+err, false); }
  probeBtn.disabled=false; probeBtn.textContent='Auto-Detect Deep Research';
}
probeBtn.addEventListener('click', runProbe);
document.querySelector('[name="target_brand"]').addEventListener('keydown',(e)=>{ if(e.key==='Enter'){ e.preventDefault(); runProbe(); } });

let pollTimer=null, startTs=0, tickTimer=null;
function fmt(sec){ const m=String(Math.floor(sec/60)).padStart(2,'0'); const s=String(sec%60).padStart(2,'0'); return m+':'+s; }

document.getElementById('auditForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target, fd = new FormData(form);
  const brand = fd.get('target_brand').trim();
  const topics = splitList(fd.get('industry_topics'));
  const comps = splitList(fd.get('competitor_entities'));
  if(!brand){ alert('Brand name required'); return; }
  if(!topics.length){ alert('At least one topic'); return; }
  if(!comps.length){ alert('At least one competitor'); return; }

  const btn=document.getElementById('runBtn');
  btn.disabled=true;
  const outBtn=document.getElementById('outputsBtn'); if(outBtn) outBtn.style.display='none';
  const consoleEl=document.getElementById('console');
  const statusEl=document.getElementById('status');
  const barwrap=document.getElementById('barwrap');
  consoleEl.style.display='block'; consoleEl.innerHTML='';
  barwrap.style.display='block';
  statusEl.textContent='Queued — starting full 10-engine live audit…';
  toast(' Full audit started — 10 micro-engines running locally.');
  startTs=Date.now();
  document.getElementById('barfill').style.width='4%';
  const pctEl=document.getElementById('pct'); if(pctEl) pctEl.textContent='4%';
  document.getElementById('stage').textContent='Initializing…';
  tickTimer=setInterval(()=>{ document.getElementById('timer').textContent=fmt(Math.floor((Date.now()-startTs)/1000)); },1000);

  const body=new URLSearchParams();
  for(const [k,v] of fd.entries()) body.append(k,v);
  let jobId=null;
  try {
    const resp=await fetch('/run',{method:'POST',body});
    const data=await resp.json();
    if(data.error){ statusEl.innerHTML='<span class="err">'+data.error+'</span>'; btn.disabled=false; return; }
    jobId=data.job;
    poll(jobId);
  } catch(err){ statusEl.innerHTML='<span class="err">Request failed: '+err+'</span>'; btn.disabled=false; }
});

function poll(jobId){
  lastJob=jobId;
  fetch('/status/'+jobId).then(r=>r.json()).then(d=>{
    const c=document.getElementById('console');
    if(d.logs){ c.innerHTML = d.logs.slice(-300).map(escLog).join('<br>'); }
    c.scrollTop=c.scrollHeight;
    if(typeof d.progress==='number'){ document.getElementById('barfill').style.width=Math.max(4,d.progress)+'%'; const p=document.getElementById('pct'); if(p) p.textContent=d.progress+'%'; }
    if(d.stage) document.getElementById('stage').textContent=d.stage;
    if(d.status==='done'){ finish(jobId); return; }
    if(d.status==='error'){ document.getElementById('status').innerHTML='<span class="err">Error: '+d.error+'</span>'; toast('Audit failed: '+d.error,'bad'); stopTimers(); document.getElementById('runBtn').disabled=false; return; }
    document.getElementById('status').textContent='Running 10-engine audit… ('+d.progress+'%)';
    pollTimer=setTimeout(()=>poll(jobId), 1000);
  }).catch(()=>{ pollTimer=setTimeout(()=>poll(jobId), 1500); });
}
function escLog(s){
  s=String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
  if(/error|fail/i.test(s)) return '<span style="color:var(--m3-error)">'+s+'</span>';
  if(/complete|verified|complete\.|done/i.test(s)) return '<span style="color:var(--m3-tertiary)">'+s+'</span>';
  return s;
}

function stopTimers(){ if(pollTimer) clearTimeout(pollTimer); if(tickTimer) clearInterval(tickTimer); }

function finish(jobId){
  lastJob=jobId;
  stopTimers();
  document.getElementById('barfill').style.width='100%';
  const p=document.getElementById('pct'); if(p) p.textContent='100%';
  document.getElementById('stage').textContent='Complete — 10/10 engines';
  document.getElementById('status').textContent='Audit complete — deep analysis ready.';
  document.getElementById('runBtn').disabled=false;
  const outBtn=document.getElementById('outputsBtn'); if(outBtn){ outBtn.style.display=''; outBtn.onclick=()=>loadOutputs(jobId); }
  toast(' Audit complete — opening in-depth 10-engine analysis.', 'ok');
  document.getElementById('page-inputs').classList.remove('active');
  loadFeatures(jobId);
}

function setStep(id, state){
  const el=document.getElementById(id);
  if(!el) return;
  el.classList.remove('active','done');
  if(state) el.classList.add(state);
}

function loadFeatures(jobId, fromTab){
  lastJob=jobId;
  const el=document.getElementById('page-features');
  el.innerHTML='<div class="card"><div class="skel" style="height:22px"></div><div class="skel" style="height:14px;margin-top:10px"></div><div class="skel" style="height:14px;margin-top:10px"></div><p class="hint">Synthesizing 10-engine deep analysis — methodology, per-engine evidence, verification…</p></div>';
  setStep('step1','done'); setStep('step2','active'); setStep('step3','');
  if(!fromTab){ document.getElementById('page-inputs').classList.remove('active'); document.getElementById('page-outputs').classList.remove('active'); }
  el.classList.add('active');
  fetch('/page/analysis/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="m3-btn" onclick="loadOutputs(\''+jobId+'\')">Show Outputs — verified report →</button><button class="m3-btn outlined" onclick="goStep(\'inputs\')">← Back to Inputs</button></div>';
    window.scrollTo({top:0, behavior:'smooth'});
  }).catch(()=>{ el.innerHTML='<div class="card err">Failed to load analysis.</div>'; });
}

function loadOutputs(jobId, fromTab){
  lastJob=jobId;
  const el=document.getElementById('page-outputs');
  el.innerHTML='<div class="card"><div class="skel" style="height:22px"></div><div class="skel" style="height:14px;margin-top:10px"></div><p class="hint">Compiling verified outputs — KPIs, proximity, citation gaps, off-page targets, downloads…</p></div>';
  setStep('step1','done'); setStep('step2','done'); setStep('step3','active');
  if(!fromTab){ document.getElementById('page-features').classList.remove('active'); }
  el.classList.add('active');
  fetch('/page/outputs/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="m3-btn outlined" onclick="backToFeatures()">← Back to Analysis</button><button class="m3-btn tonal" onclick="goStep(\'inputs\')">＋ New Audit</button></div>';
    window.scrollTo({top:0, behavior:'smooth'});
    toast(' Outputs ready — verified competitive report below.', 'ok');
  }).catch(()=>{ el.innerHTML='<div class="card err">Failed to load outputs.</div>'; });
}

function backToFeatures(){
  setStep('step3','');
  document.getElementById('page-outputs').classList.remove('active');
  setStep('step2','active');
  document.getElementById('page-features').classList.add('active');
  window.scrollTo(0,0);
}
