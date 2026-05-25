// ============ Time Tracker (localStorage) ============
const LS_ENTRIES = 'tt_entries_v1';
const LS_RUNNING = 'tt_running_v1';
const LS_QUICKS  = 'tt_quicks_v1';

const $ = (id)=>document.getElementById(id);
const fmtDur = (ms)=>{
  if(ms<0) ms=0;
  const s=Math.floor(ms/1000);
  const h=Math.floor(s/3600);
  const m=Math.floor((s%3600)/60);
  const ss=s%60;
  return (h>0?String(h).padStart(2,'0')+':':'')+String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0');
};
const fmtHM = (ms)=>{
  const min=Math.round(ms/60000);
  const h=Math.floor(min/60);
  const m=min%60;
  return (h>0?h+'h ':'')+m+'m';
};
const fmtTime = (ts)=>{
  const d=new Date(ts);
  return d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
};
const fmtDate = (ts)=>new Date(ts).toLocaleDateString();
const todayKey = (ts=Date.now())=>{
  const d=new Date(ts); d.setHours(0,0,0,0); return d.getTime();
};
const isSameDay = (a,b)=>todayKey(a)===todayKey(b);

function loadEntries(){ try{return JSON.parse(localStorage.getItem(LS_ENTRIES)||'[]')}catch(e){return []} }
function saveEntries(arr){ localStorage.setItem(LS_ENTRIES, JSON.stringify(arr)) }
function loadRunning(){ try{return JSON.parse(localStorage.getItem(LS_RUNNING)||'null')}catch(e){return null} }
function saveRunning(r){ r?localStorage.setItem(LS_RUNNING, JSON.stringify(r)):localStorage.removeItem(LS_RUNNING) }
function loadQuicks(){
  try{ const q=JSON.parse(localStorage.getItem(LS_QUICKS)||'null'); return q||['Email','Lunch','Break','Meeting','Research','Log Analysis']; }
  catch(e){ return ['Email','Lunch','Break','Meeting']; }
}
function saveQuicks(arr){ localStorage.setItem(LS_QUICKS, JSON.stringify(arr.slice(0,12))) }

// ===== Tabs =====
document.querySelectorAll('nav button').forEach(b=>{
  b.onclick = ()=>{
    document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    ['tracker','today','trends','data'].forEach(t=>$('tab-'+t).classList.add('hidden'));
    $('tab-'+b.dataset.tab).classList.remove('hidden');
    if(b.dataset.tab==='today') renderToday();
    if(b.dataset.tab==='trends') renderTrends();
    if(b.dataset.tab==='data') renderAll();
  };
});

// ===== Start / Stop =====
function start(name, category){
  name=(name||'').trim();
  if(!name){ alert('请输入任务名'); return; }
  // stop running first
  if(loadRunning()) stop();
  const r={name, category:category||'work', start:Date.now()};
  saveRunning(r);
  // update quick picks
  const qs=loadQuicks();
  if(!qs.includes(name)){ qs.unshift(name); saveQuicks(qs); }
  $('taskName').value='';
  renderRunning(); renderQuicks(); renderTodayList();
}
function stop(){
  const r=loadRunning();
  if(!r) return;
  const end=Date.now();
  if(end-r.start>=1000){ // ignore < 1s
    const entries=loadEntries();
    entries.push({id:Date.now()+'_'+Math.random().toString(36).slice(2,7), name:r.name, category:r.category, start:r.start, end});
    saveEntries(entries);
  }
  saveRunning(null);
  renderRunning(); renderTodayList();
}

$('startBtn').onclick=()=>start($('taskName').value, $('taskCategory').value);
$('taskName').addEventListener('keydown',e=>{ if(e.key==='Enter') start($('taskName').value, $('taskCategory').value); });

// ===== Render running =====
let tickHandle=null;
function renderRunning(){
  const box=$('runningBox');
  const r=loadRunning();
  if(!r){ box.innerHTML=''; if(tickHandle){clearInterval(tickHandle);tickHandle=null;} return; }
  const tagClass = r.category==='work'?'tag-work':r.category==='break'?'tag-break':'tag-other';
  const update = ()=>{
    box.innerHTML=`<div class="running">
      <div><span class="name">${escapeHtml(r.name)}</span><span class="tag ${tagClass}">${r.category}</span><br><small style="color:var(--muted)">开始于 ${fmtTime(r.start)}</small></div>
      <div><span class="elapsed">${fmtDur(Date.now()-r.start)}</span> <button class="btn btn-stop" id="stopBtn">⏹ Stop</button></div>
    </div>`;
    $('stopBtn').onclick=stop;
  };
  update();
  if(tickHandle) clearInterval(tickHandle);
  tickHandle=setInterval(update,1000);
}

function escapeHtml(s){return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

// ===== Quick picks =====
function renderQuicks(){
  const qs=loadQuicks();
  $('quickPicks').innerHTML='<small style="color:var(--muted)">快捷：</small> '+qs.map(q=>`<span data-q="${escapeHtml(q)}">${escapeHtml(q)}</span>`).join('');
  $('quickPicks').querySelectorAll('span[data-q]').forEach(el=>{
    el.onclick=()=>{ $('taskName').value=el.dataset.q; $('taskName').focus(); };
  });
}

// ===== Today list =====
function renderTodayList(){
  const entries=loadEntries().filter(e=>isSameDay(e.start, Date.now())).sort((a,b)=>b.start-a.start);
  if(entries.length===0){
    $('todayList').innerHTML='<p style="color:var(--muted)">今天还没有记录。</p>';
    return;
  }
  let html='<table><thead><tr><th>开始</th><th>结束</th><th>任务</th><th>分类</th><th>时长</th><th></th></tr></thead><tbody>';
  for(const e of entries){
    const tagClass = e.category==='work'?'tag-work':e.category==='break'?'tag-break':'tag-other';
    html+=`<tr>
      <td>${fmtTime(e.start)}</td>
      <td>${fmtTime(e.end)}</td>
      <td>${escapeHtml(e.name)}</td>
      <td><span class="tag ${tagClass}">${e.category}</span></td>
      <td class="dur">${fmtDur(e.end-e.start)}</td>
      <td class="row-actions"><button data-del="${e.id}">删除</button></td>
    </tr>`;
  }
  html+='</tbody></table>';
  $('todayList').innerHTML=html;
  $('todayList').querySelectorAll('button[data-del]').forEach(b=>{
    b.onclick=()=>{ if(confirm('删除此条记录？')){ saveEntries(loadEntries().filter(x=>x.id!==b.dataset.del)); renderTodayList(); } };
  });
}

// ===== Today summary =====
let todayChartObj=null;
function renderToday(){
  const entries=loadEntries().filter(e=>isSameDay(e.start, Date.now()));
  let work=0,brk=0,other=0;
  for(const e of entries){
    const d=e.end-e.start;
    if(e.category==='work') work+=d;
    else if(e.category==='break') brk+=d;
    else other+=d;
  }
  $('todayStats').innerHTML=`
    <div class="stat"><div class="label">工作</div><div class="value">${fmtHM(work)}</div></div>
    <div class="stat"><div class="label">休息</div><div class="value">${fmtHM(brk)}</div></div>
    <div class="stat"><div class="label">其他</div><div class="value">${fmtHM(other)}</div></div>
    <div class="stat"><div class="label">总记录</div><div class="value">${entries.length}</div></div>
  `;

  // group by name
  const map=new Map();
  for(const e of entries){
    const k=e.name+'||'+e.category;
    if(!map.has(k)) map.set(k,{name:e.name,category:e.category,count:0,total:0});
    const g=map.get(k); g.count++; g.total+=e.end-e.start;
  }
  const groups=[...map.values()].sort((a,b)=>b.total-a.total);
  const tbody=$('todayGroupTable').querySelector('tbody');
  tbody.innerHTML=groups.map(g=>{
    const tagClass = g.category==='work'?'tag-work':g.category==='break'?'tag-break':'tag-other';
    return `<tr><td>${escapeHtml(g.name)}</td><td><span class="tag ${tagClass}">${g.category}</span></td><td>${g.count}</td><td class="dur">${fmtHM(g.total)}</td></tr>`;
  }).join('') || '<tr><td colspan="4" style="color:var(--muted)">无</td></tr>';

  // chart
  const labels=groups.slice(0,10).map(g=>g.name);
  const data=groups.slice(0,10).map(g=>Math.round(g.total/60000));
  if(todayChartObj) todayChartObj.destroy();
  todayChartObj=new Chart($('todayChart'),{
    type:'bar',
    data:{labels,datasets:[{label:'分钟',data,backgroundColor:'#38bdf8'}]},
    options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'}}}}
  });
}

// ===== Trends =====
let trendChartObj=null;
function setRange(days){
  const to=new Date(); to.setHours(0,0,0,0);
  const from=new Date(to); from.setDate(from.getDate()-(days-1));
  $('trendFrom').value=from.toISOString().slice(0,10);
  $('trendTo').value=to.toISOString().slice(0,10);
  renderTrends();
}
function renderTrends(){
  if(!$('trendFrom').value || !$('trendTo').value){ setRange(7); return; }
  const from=new Date($('trendFrom').value); from.setHours(0,0,0,0);
  const to=new Date($('trendTo').value); to.setHours(23,59,59,999);
  const entries=loadEntries().filter(e=>e.start>=from.getTime() && e.start<=to.getTime());

  // per day buckets
  const days=[]; const cur=new Date(from);
  while(cur<=to){ days.push(new Date(cur)); cur.setDate(cur.getDate()+1); }
  const dayLabels=days.map(d=>d.toLocaleDateString([], {month:'numeric',day:'numeric'}));
  const workArr=Array(days.length).fill(0), brkArr=Array(days.length).fill(0), otherArr=Array(days.length).fill(0);
  for(const e of entries){
    const idx=Math.floor((todayKey(e.start)-todayKey(from.getTime()))/86400000);
    if(idx<0||idx>=days.length) continue;
    const dur=(e.end-e.start)/60000;
    if(e.category==='work') workArr[idx]+=dur;
    else if(e.category==='break') brkArr[idx]+=dur;
    else otherArr[idx]+=dur;
  }

  let totW=0,totB=0,totO=0;
  for(let i=0;i<days.length;i++){ totW+=workArr[i]; totB+=brkArr[i]; totO+=otherArr[i]; }
  const totalDays=days.length;
  $('trendStats').innerHTML=`
    <div class="stat"><div class="label">总工作</div><div class="value">${fmtHM(totW*60000)}</div></div>
    <div class="stat"><div class="label">总休息</div><div class="value">${fmtHM(totB*60000)}</div></div>
    <div class="stat"><div class="label">总其他</div><div class="value">${fmtHM(totO*60000)}</div></div>
    <div class="stat"><div class="label">日均工作</div><div class="value">${fmtHM(totW*60000/totalDays)}</div></div>
  `;

  if(trendChartObj) trendChartObj.destroy();
  trendChartObj=new Chart($('trendChart'),{
    type:'bar',
    data:{labels:dayLabels,datasets:[
      {label:'工作(分)',data:workArr.map(v=>Math.round(v)),backgroundColor:'#38bdf8',stack:'s'},
      {label:'休息(分)',data:brkArr.map(v=>Math.round(v)),backgroundColor:'#eab308',stack:'s'},
      {label:'其他(分)',data:otherArr.map(v=>Math.round(v)),backgroundColor:'#94a3b8',stack:'s'},
    ]},
    options:{responsive:true,plugins:{legend:{labels:{color:'#e2e8f0'}}},scales:{x:{stacked:true,ticks:{color:'#94a3b8'}},y:{stacked:true,ticks:{color:'#94a3b8'}}}}
  });

  // top tasks
  const map=new Map();
  for(const e of entries){
    const k=e.name+'||'+e.category;
    if(!map.has(k)) map.set(k,{name:e.name,category:e.category,total:0});
    map.get(k).total+=e.end-e.start;
  }
  const grandTotal=[...map.values()].reduce((s,g)=>s+g.total,0)||1;
  const top=[...map.values()].sort((a,b)=>b.total-a.total).slice(0,20);
  const tbody=$('trendTopTable').querySelector('tbody');
  tbody.innerHTML=top.map((g,i)=>{
    const tagClass = g.category==='work'?'tag-work':g.category==='break'?'tag-break':'tag-other';
    const pct=(g.total/grandTotal*100).toFixed(1);
    return `<tr><td>${i+1}</td><td>${escapeHtml(g.name)}</td><td><span class="tag ${tagClass}">${g.category}</span></td><td class="dur">${fmtHM(g.total)}</td><td>${pct}%</td></tr>`;
  }).join('') || '<tr><td colspan="5" style="color:var(--muted)">无数据</td></tr>';
}

$('trendRefresh').onclick=renderTrends;
$('trendWeek').onclick=()=>setRange(7);
$('trendMonth').onclick=()=>setRange(30);

// ===== Data tab =====
function renderAll(){
  const entries=loadEntries().sort((a,b)=>b.start-a.start).slice(0,200);
  const tbody=$('allTable').querySelector('tbody');
  tbody.innerHTML=entries.map(e=>{
    const tagClass = e.category==='work'?'tag-work':e.category==='break'?'tag-break':'tag-other';
    return `<tr>
      <td>${fmtDate(e.start)} ${fmtTime(e.start)}</td>
      <td>${fmtTime(e.end)}</td>
      <td>${escapeHtml(e.name)}</td>
      <td><span class="tag ${tagClass}">${e.category}</span></td>
      <td class="dur">${fmtDur(e.end-e.start)}</td>
      <td class="row-actions"><button data-del="${e.id}">删除</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" style="color:var(--muted)">无数据</td></tr>';
  tbody.querySelectorAll('button[data-del]').forEach(b=>{
    b.onclick=()=>{ if(confirm('删除此条？')){ saveEntries(loadEntries().filter(x=>x.id!==b.dataset.del)); renderAll(); renderTodayList(); } };
  });
}

$('exportBtn').onclick=()=>{
  const blob=new Blob([JSON.stringify({entries:loadEntries(),quicks:loadQuicks(),exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob); const a=document.createElement('a');
  a.href=url; a.download=`timetracker_${new Date().toISOString().slice(0,10)}.json`; a.click();
  URL.revokeObjectURL(url);
};
$('exportCsvBtn').onclick=()=>{
  const rows=[['start','end','duration_min','name','category']];
  for(const e of loadEntries()){
    rows.push([new Date(e.start).toISOString(),new Date(e.end).toISOString(),((e.end-e.start)/60000).toFixed(2),'"'+e.name.replace(/"/g,'""')+'"',e.category]);
  }
  const csv=rows.map(r=>r.join(',')).join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const url=URL.createObjectURL(blob); const a=document.createElement('a');
  a.href=url; a.download=`timetracker_${new Date().toISOString().slice(0,10)}.csv`; a.click();
  URL.revokeObjectURL(url);
};
$('importBtn').onclick=()=>$('importFile').click();
$('importFile').onchange=(ev)=>{
  const f=ev.target.files[0]; if(!f) return;
  const reader=new FileReader();
  reader.onload=()=>{
    try{
      const obj=JSON.parse(reader.result);
      if(!Array.isArray(obj.entries)) throw new Error('格式错误');
      if(confirm(`导入 ${obj.entries.length} 条记录？(会与现有数据合并，按 id 去重)`)){
        const existing=loadEntries(); const ids=new Set(existing.map(e=>e.id));
        const merged=existing.concat(obj.entries.filter(e=>!ids.has(e.id)));
        saveEntries(merged);
        if(Array.isArray(obj.quicks)) saveQuicks(obj.quicks);
        alert('导入完成'); renderAll(); renderTodayList(); renderQuicks();
      }
    }catch(e){ alert('导入失败: '+e.message); }
  };
  reader.readAsText(f);
};
$('clearBtn').onclick=()=>{
  if(confirm('确定清空全部记录？此操作不可恢复！')){
    if(confirm('再次确认：真的要清空？')){
      localStorage.removeItem(LS_ENTRIES); localStorage.removeItem(LS_RUNNING);
      renderAll(); renderTodayList(); renderRunning();
    }
  }
};

// ============ Pomodoro ============
const LS_POMO = 'tt_pomo_v1';
const LS_POMO_CFG = 'tt_pomo_cfg_v1';

function loadPomo(){ try{return JSON.parse(localStorage.getItem(LS_POMO)||'null')}catch(e){return null} }
function savePomo(p){ p?localStorage.setItem(LS_POMO, JSON.stringify(p)):localStorage.removeItem(LS_POMO) }
function loadPomoCfg(){
  try{ return JSON.parse(localStorage.getItem(LS_POMO_CFG)||'null') || {work:25,brk:5,long:15,cycle:4} }
  catch(e){ return {work:25,brk:5,long:15,cycle:4} }
}
function savePomoCfg(c){ localStorage.setItem(LS_POMO_CFG, JSON.stringify(c)) }

// init config inputs
(function initPomoCfg(){
  const c=loadPomoCfg();
  $('pomoWork').value=c.work; $('pomoBreak').value=c.brk;
  $('pomoLong').value=c.long; $('pomoCycle').value=c.cycle;
  ['pomoWork','pomoBreak','pomoLong','pomoCycle'].forEach(id=>{
    $(id).addEventListener('change',()=>{
      savePomoCfg({
        work:+$('pomoWork').value||25, brk:+$('pomoBreak').value||5,
        long:+$('pomoLong').value||15, cycle:+$('pomoCycle').value||4
      });
    });
  });
})();

function startPomo(phase){
  const c=loadPomoCfg();
  const mins = phase==='work'?c.work : phase==='long'?c.long : c.brk;
  const completed = (loadPomo()||{}).completed || 0;
  const p={phase, start:Date.now(), duration:mins*60*1000, completed};
  savePomo(p);
  renderPomo();
}
function stopPomo(){
  savePomo(null); renderPomo();
}
function onPomoComplete(){
  const p=loadPomo(); if(!p) return;
  const c=loadPomoCfg();
  let newCompleted = p.completed;
  let nextPhase;
  if(p.phase==='work'){
    newCompleted = p.completed+1;
    nextPhase = (newCompleted % c.cycle === 0) ? 'long' : 'brk';
  } else {
    nextPhase = 'work';
  }
  notify(p.phase==='work' ? '🍅 一个番茄结束，可以歇会儿了' : '⏰ 休息结束');
  // 番茄钟纯提醒，不动任务计时；停在 waiting 状态等用户决定下一段
  savePomo({phase:nextPhase, start:null, duration:(nextPhase==='work'?c.work:nextPhase==='long'?c.long:c.brk)*60*1000, completed:newCompleted, waiting:true});
  renderPomo();
}
function notify(msg){
  try{
    if('Notification' in window){
      if(Notification.permission==='granted'){ new Notification('Time Tracker', {body:msg}); }
      else if(Notification.permission!=='denied'){ Notification.requestPermission().then(p=>{if(p==='granted') new Notification('Time Tracker',{body:msg});}); }
    }
  }catch(e){}
  // audible beep
  try{
    const ctx=new (window.AudioContext||window.webkitAudioContext)();
    [0,0.18,0.36].forEach((t,i)=>{
      const o=ctx.createOscillator(), g=ctx.createGain();
      o.frequency.value=i===2?1046:880; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.0001,ctx.currentTime+t);
      g.gain.exponentialRampToValueAtTime(0.3,ctx.currentTime+t+0.02);
      g.gain.exponentialRampToValueAtTime(0.0001,ctx.currentTime+t+0.15);
      o.start(ctx.currentTime+t); o.stop(ctx.currentTime+t+0.16);
    });
  }catch(e){}
  // flash title
  let n=0; const orig=document.title;
  const h=setInterval(()=>{ document.title = (n++%2===0)?'🔔 '+msg:orig; if(n>10){clearInterval(h); document.title=orig;} },600);
}

let pomoTick=null;
function renderPomo(){
  const box=$('pomoBox'); const p=loadPomo(); const c=loadPomoCfg();
  if(pomoTick){clearInterval(pomoTick); pomoTick=null;}
  if(!p){
    box.innerHTML = `
      <button class="btn btn-start" id="pomoStartWork">▶ 开始 ${c.work} 分钟工作</button>
      <button class="btn btn-secondary" id="pomoStartBreak" style="margin-left:8px">☕ ${c.brk} 分钟休息</button>
      <small style="color:var(--muted);margin-left:10px">今日完成: ${countTodayPomos()} 🍅</small>
    `;
    $('pomoStartWork').onclick=()=>startPomo('work');
    $('pomoStartBreak').onclick=()=>startPomo('brk');
    return;
  }
  if(p.waiting){
    const label = p.phase==='work'?'工作':p.phase==='long'?'长休息':'休息';
    const mins = Math.round(p.duration/60000);
    box.innerHTML = `<div class="running" style="border-color:var(--yellow)">
      <div><span class="name">下一段：${label} (${mins} 分钟)</span><br><small style="color:var(--muted)">已完成 ${p.completed} 个 🍅</small></div>
      <div><button class="btn btn-start" id="pomoGo">▶ 开始</button>
      <button class="btn btn-secondary" id="pomoSkip" style="margin-left:6px">跳过</button></div>
    </div>`;
    $('pomoGo').onclick=()=>startPomo(p.phase);
    $('pomoSkip').onclick=()=>stopPomo();
    return;
  }
  const update=()=>{
    const remain = p.start + p.duration - Date.now();
    if(remain<=0){ onPomoComplete(); return; }
    const label = p.phase==='work'?'🍅 工作中':p.phase==='long'?'☕ 长休息':'☕ 休息中';
    const color = p.phase==='work'?'var(--green)':'var(--yellow)';
    box.innerHTML = `<div class="running" style="border-color:${color}">
      <div><span class="name" style="color:${color}">${label}</span><br><small style="color:var(--muted)">已完成 ${p.completed} 个 🍅 · 第 ${(p.completed % c.cycle)+1}/${c.cycle} 周期</small></div>
      <div><span class="elapsed" style="color:${color}">${fmtDur(remain)}</span>
      <button class="btn btn-stop" id="pomoCancel" style="margin-left:6px">取消</button></div>
    </div>`;
    $('pomoCancel').onclick=()=>{ if(confirm('取消当前番茄钟？')) stopPomo(); };
  };
  update();
  pomoTick=setInterval(update,500);
}
function countTodayPomos(){
  // count work pomos completed today: from the entry log we can't tell pomos directly,
  // but we tracked p.completed; reset across days by checking last savePomo date is complicated.
  // Simple: store daily counter in localStorage.
  const key='tt_pomo_day_'+todayKey();
  return +(localStorage.getItem(key)||0);
}
function bumpTodayPomos(){
  const key='tt_pomo_day_'+todayKey();
  localStorage.setItem(key, (+(localStorage.getItem(key)||0))+1);
}
// hook into onPomoComplete: when work completes, bump
const _origOnPomoComplete = onPomoComplete;
onPomoComplete = function(){
  const p=loadPomo();
  if(p && p.phase==='work') bumpTodayPomos();
  _origOnPomoComplete();
};

// request notification permission early
if('Notification' in window && Notification.permission==='default'){
  setTimeout(()=>{ try{Notification.requestPermission()}catch(e){} }, 2000);
}

// ===== Init =====
renderRunning();
renderQuicks();
renderTodayList();
renderPomo();
setRange(7); // pre-set trend range
