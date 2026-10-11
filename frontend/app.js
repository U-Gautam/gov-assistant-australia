import {loadHistory, saveHistory, newSessionId, safeLink, MAX_SESSIONS, MAX_MESSAGES} from './history.mjs';

const suggestions = {
  tax: [
    ['Income tax basics','What is income tax?'],
    ['Apply for a TFN','How do I apply for a tax file number?'],
    ['Lodge a return','How do I lodge my tax return online?'],
    ['Claim deductions','Can I claim work expenses on my tax return?'],
    ['Tax deadline','When is my tax return due?'],
    ['Create myGov','How do I create a myGov account?'],
    ['Super basics','What is superannuation?'],
  ],
  visa: [
    ['Student visa changes','What changed for student visas on 2 October 2026?'],
    ['Student work rights','Can I work on a Student visa?'],
    ['Student health cover','What is OSHC for a Student visa?'],
    ['Graduate visa','Can I get a Temporary Graduate visa after study?'],
    ['Check conditions','Where can I check the conditions on a visa I hold?'],
    ['Application status','How do I check the status of a visa application I lodged online?'],
    ['Family rules','Can family join me later on a Student visa?'],
    ['Provider transfers','What changed for student provider transfers in October 2026?'],
  ],
};

const messages = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('question');
const suggestionsEl = document.getElementById('suggestions');
const topicButtons = [...document.querySelectorAll('.topic-card')];
const historyDialog = document.getElementById('history-dialog');
const historyList = document.getElementById('history-list');
const historyCount = document.getElementById('history-count');
const historyClear = document.getElementById('history-clear');
const sendButton = form.querySelector('button[type="submit"]');
const status = document.getElementById('chat-status');
const siteStatus = document.getElementById('site-status');
const sourcesDialog = document.getElementById('sources-dialog');
const sourcesList = document.getElementById('sources-list');
const sourcesStatus = document.getElementById('sources-status');
const sourceFilterButtons = [...document.querySelectorAll('[data-source-topic]')];
const localStore = (()=>{try{return window.localStorage}catch{return null}})();
const historyState = loadHistory(localStore);
let topic = 'tax';
let currentMessages = [];
let pending = false;
let indexedSources = [];
let sourceFilter = 'all';
let healthInfo = null;
let sourcesLoaded = false;

const starterQuestions = [
  ['Tax file number', 'How do I apply for a tax file number?', 'tax'],
  ['Lost TFN', 'I lost my TFN. Where can I find it?', 'tax'],
  ['After graduation', 'I’m graduating as an international student in Australia. What should I do next?', 'visa'],
  ['Student visa update', 'What changed for student visas on 2 October 2026?', 'visa'],
  ['Current visa fee', 'Can you tell me the current Student visa fee?', 'visa'],
  ['Private visa record', 'Can you access my visa decision?', 'visa'],
];

function formatDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '';
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('en-AU',{day:'numeric',month:'short',year:'numeric'}).format(date);
}

function showStarterQuestions() {
  if (document.getElementById('empty-state')) return;
  const section=document.createElement('section');
  section.id='empty-state';
  section.className='empty-state';
  const kicker=document.createElement('span');kicker.className='eyebrow';kicker.textContent='START WITH AN EXAMPLE';
  const heading=document.createElement('h3');heading.textContent='Pick a question or write your own';
  const grid=document.createElement('div');grid.className='example-grid';
  for (const [label,question,questionTopic] of starterQuestions) {
    const button=document.createElement('button');
    button.type='button';button.dataset.question=question;button.dataset.topic=questionTopic;
    const title=document.createElement('strong');title.textContent=label;
    const sub=document.createElement('span');sub.textContent=question;
    button.append(title,sub);grid.append(button);
  }
  section.append(kicker,heading,grid);
  messages.append(section);
}

function addMessage(text, role='assistant', links=[], steps=[], record=true, mode='', details=null, feedback=null, storedMessage=null) {
  const entry=storedMessage || {text,role,links,steps,mode,details,feedback};
  if (record) {
    currentMessages.push(entry);
    persistActive();
  }
  if (role==='user') document.getElementById('empty-state')?.remove();
  const row = document.createElement('div');
  row.className = `message ${role}-message`;
  if (role === 'assistant') {
    const avatar = document.createElement('span');
    avatar.className = 'avatar';
    avatar.setAttribute('aria-hidden','true');
    avatar.textContent = 'ga';
    row.append(avatar);
  }
  const body = document.createElement('div');
  body.className = 'message-body';
  const para = document.createElement('p');
  para.textContent = text;
  body.append(para);
  if (role==='assistant' && mode) {
    const label=document.createElement('small');
    label.className='answer-mode';
    label.textContent=mode==='ollama' ? 'LOCAL AI SUMMARY · CHECK THE SOURCES' : (mode==='abstain' ? 'NO MATCHING SOURCE NOTE' : (mode==='guidance' ? 'HOW TO USE THIS ASSISTANT' : 'SOURCE EXTRACT'));
    body.append(label);
  }
  if (steps.length) {
    const list = document.createElement('ol');
    list.className = 'answer-steps';
    for (const step of steps) {
      const item = document.createElement('li');
      item.textContent = step;
      list.append(item);
    }
    body.append(list);
  }
  if (links.length) {
    const sourceList = document.createElement('div');
    sourceList.className = 'source-list';
    const title = document.createElement('span');
    title.className = 'source-title';
    title.textContent = links.length===1 ? 'CHECK ON THE OFFICIAL SITE' : 'CHECK ON OFFICIAL SITES';
    sourceList.append(title);
    for (const source of links.map(safeLink).filter(Boolean)) {
      const link = document.createElement('a');
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = source.label;
      sourceList.append(link);
    }
    body.append(sourceList);
  }
  if (role==='assistant' && mode && details) {
    const disclosure=document.createElement('details');
    disclosure.className='retrieval-details';
    const summary=document.createElement('summary');summary.textContent='Show retrieval details';
    disclosure.append(summary);
    const count=document.createElement('p');
    const retrieved=Number.isInteger(details.retrieved)?details.retrieved:(Array.isArray(details.evidence)?details.evidence.length:0);
    count.textContent=`${retrieved} matching source ${retrieved===1?'note':'notes'} · Answer mode: ${mode==='ollama'?'local AI summary':mode==='abstain'?'no matching source note':'source extract'}`;
    disclosure.append(count);
    if (details.generation && details.generation!=='none') {
      const reason=document.createElement('p');
      reason.textContent=`Generation route: ${String(details.generation).replaceAll('_',' ')}`;
      disclosure.append(reason);
    }
    if (details.reason && details.reason!=='ok') {
      const route=document.createElement('p');
      route.textContent=`Retrieval route: ${String(details.reason).replaceAll('_',' ')}`;
      disclosure.append(route);
    }
    if (Array.isArray(details.evidence) && details.evidence.length) {
      const list=document.createElement('ol');
      for (const note of details.evidence) {
        const item=document.createElement('li');
        const source=safeLink({label:note.title,url:note.url});
        if (!source) continue;
        const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.label;
        item.append(link);
        const meta=document.createElement('small');meta.textContent=`${note.agency || 'Official source'}${formatDate(note.reviewed_on)?` · Source-note date ${formatDate(note.reviewed_on)}`:''}`;
        item.append(meta);list.append(item);
      }
      disclosure.append(list);
    }
    body.append(disclosure);
  }
  if (role==='assistant' && mode) {
    const feedbackRow=document.createElement('div');feedbackRow.className='answer-feedback';
    const prompt=document.createElement('span');prompt.textContent='Helpful? Saved on this device';feedbackRow.append(prompt);
    for (const [value,label,symbol] of [['up','Helpful','👍'],['down','Not helpful','👎']]) {
      const button=document.createElement('button');button.type='button';button.className='feedback-button';
      button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(entry.feedback===value));
      button.textContent=symbol;
      button.addEventListener('click',()=>{
        entry.feedback=entry.feedback===value?null:value;
        feedbackRow.querySelectorAll('button').forEach(item=>item.setAttribute('aria-pressed',String(item===button && entry.feedback===value)));
        persistActive();
      });
      feedbackRow.append(button);
    }
    body.append(feedbackRow);
  }
  row.append(body);
  messages.append(row);
  messages.scrollTop = messages.scrollHeight;
}

function persistHistory() {
  historyState.sessions.sort((a,b)=>b.updatedAt-a.updatedAt);
  historyState.sessions = historyState.sessions.slice(0,MAX_SESSIONS);
  const saved=saveHistory(localStore,historyState);
  historyCount.textContent = String(historyState.sessions.length);
  historyClear.disabled = historyState.sessions.length===0;
  if (!saved) document.getElementById('history-note').textContent='This browser is not allowing local storage. Chats will be lost when this page closes.';
}

function persistActive() {
  if (!historyState.activeId) return;
  const session = historyState.sessions.find(item=>item.id===historyState.activeId);
  if (!session) return;
  session.topic=topic;
  session.updatedAt=Date.now();
  currentMessages=currentMessages.slice(-MAX_MESSAGES);
  session.messages=currentMessages;
  persistHistory();
  if (historyDialog.open) renderHistory();
}

function ensureSession(title) {
  if (historyState.activeId) return;
  const now=Date.now();
  const id=newSessionId();
  historyState.sessions.unshift({id,title:title.slice(0,65),topic,createdAt:now,updatedAt:now,messages:currentMessages.slice()});
  historyState.activeId=id;
  persistHistory();
}

function restoreSession(id) {
  const session=historyState.sessions.find(item=>item.id===id);
  if (!session) return;
  historyState.activeId=id;
  topic=session.topic;
  currentMessages=session.messages.map(item=>({...item}));
  messages.replaceChildren();
  setTopic(topic);
  currentMessages.forEach(item=>addMessage(item.text,item.role,item.links,item.steps,false,item.mode,item.details,item.feedback,item));
  persistHistory();
  if (historyDialog.open) historyDialog.close();
  input.focus();
}

function deleteSession(id) {
  historyState.sessions=historyState.sessions.filter(item=>item.id!==id);
  if (historyState.activeId===id) resetChat();
  else persistHistory();
  renderHistory();
}

function renderHistory() {
  historyList.replaceChildren();
  if (!historyState.sessions.length) {
    const empty=document.createElement('li');
    empty.className='history-empty';
    empty.textContent='No saved chats yet. Ask a question to start one.';
    historyList.append(empty);
  }
  for (const session of historyState.sessions) {
    const row=document.createElement('li');
    row.className='history-item';
    const open=document.createElement('button');
    open.type='button';open.className='history-entry';open.dataset.id=session.id;
    const title=document.createElement('strong');title.textContent=session.title;
    const date=document.createElement('small');date.textContent=new Intl.DateTimeFormat('en-AU',{day:'numeric',month:'short',year:'numeric'}).format(session.updatedAt);
    open.append(title,date);
    const remove=document.createElement('button');
    remove.type='button';remove.className='history-delete';remove.dataset.deleteId=session.id;
    remove.setAttribute('aria-label',`Delete chat: ${session.title}`);remove.textContent='Delete';
    row.append(open,remove);historyList.append(row);
  }
  historyCount.textContent=String(historyState.sessions.length);
  historyClear.disabled=historyState.sessions.length===0;
}

function updateSiteStatus() {
  if (!healthInfo && !indexedSources.length) {
    siteStatus.textContent='Source status is unavailable.';
    return;
  }
  const count=Number.isInteger(healthInfo?.approved_source_notes) ? healthInfo.approved_source_notes : indexedSources.length;
  const pages=Number.isInteger(healthInfo?.indexed_source_pages) ? healthInfo.indexed_source_pages : new Set(indexedSources.map(item=>item.url)).size;
  const latest=indexedSources.map(item=>item.reviewed_on).filter(value=>/^\d{4}-\d{2}-\d{2}$/.test(value || '')).sort().at(-1);
  const parts=[`${count} indexed source ${count===1?'note':'notes'} from ${pages} government ${pages===1?'page':'pages'}`];
  if (latest) parts.push(`latest note date ${formatDate(latest)}`);
  parts.push(healthInfo?.ollama_model ? `local model configured: ${healthInfo.ollama_model}` : 'source-extract mode available');
  siteStatus.textContent=parts.join(' · ');
}

function renderSourceList() {
  sourcesList.replaceChildren();
  sourceFilterButtons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.sourceTopic===sourceFilter)));
  if (!sourcesLoaded) {
    sourcesStatus.textContent='The source directory is unavailable. Try again after the local service starts.';
    return;
  }
  const visible=indexedSources.filter(item=>sourceFilter==='all'||item.topic===sourceFilter);
  sourcesStatus.textContent=indexedSources.length ? `${visible.length} indexed source ${visible.length===1?'note':'notes'}${sourceFilter==='all'?'':` for ${sourceFilter==='tax'?'tax':'visas'}`}` : 'No source notes are currently available.';
  for (const note of visible) {
    const safe=safeLink({label:note.title,url:note.url});
    if (!safe) continue;
    const row=document.createElement('li');row.className='directory-item';
    const agency=document.createElement('span');agency.className='directory-agency';agency.textContent=note.agency;
    const title=document.createElement('a');title.href=safe.url;title.target='_blank';title.rel='noopener noreferrer';title.textContent=safe.label;
    const meta=document.createElement('small');meta.textContent=`${note.topic==='visa'?'Visa':'Tax'} · Source-note date ${formatDate(note.reviewed_on)||'not recorded'}`;
    row.append(agency,title,meta);sourcesList.append(row);
  }
}

async function loadSiteInfo() {
  const [healthResult,sourcesResult]=await Promise.allSettled([
    fetch('/api/health').then(response=>{if(!response.ok)throw Error('Health unavailable');return response.json()}),
    fetch('/api/sources').then(response=>{if(!response.ok)throw Error('Sources unavailable');return response.json()}),
  ]);
  if (healthResult.status==='fulfilled' && healthResult.value && typeof healthResult.value==='object') healthInfo=healthResult.value;
  if (sourcesResult.status==='fulfilled' && Array.isArray(sourcesResult.value)) {
    sourcesLoaded=true;
    indexedSources=sourcesResult.value.filter(item=>item && ['tax','visa'].includes(item.topic) && typeof item.title==='string' && typeof item.agency==='string' && safeLink({label:item.title,url:item.url}));
    renderSourceList();
  } else {
    renderSourceList();
  }
  updateSiteStatus();
}

function setTopic(next, announce=false) {
  topic = next === 'visa' ? 'visa' : 'tax';
  topicButtons.forEach(button=>{
    const active = button.dataset.topic === topic;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  });
  suggestionsEl.replaceChildren();
  for (const [label,question] of suggestions[topic]) {
    const button=document.createElement('button');
    button.type='button';
    button.dataset.question=question;
    button.textContent=label;
    suggestionsEl.append(button);
  }
  if (announce) addMessage(topic==='visa' ? 'Visas & immigration selected. Ask about applications, conditions or the October 2026 Student visa changes.' : 'Tax & the ATO selected. Ask about TFNs, returns or super.');
}

function containsPrivateDetails(value) {
  return /\b(?:\d[ -]?){8,12}\b|\b(?:my|the)\s+(?:tfn|passport number|password|medicare number|address|date of birth|dob|bank account)\s+(?:is|:)\s*\S+|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\b(?:\+?61|0)[ -]?(?:\d[ -]?){8,9}\b/i.test(value);
}

async function send(question) {
  const trimmed=String(question).trim().slice(0,500);
  if (!trimmed) return {kind:'empty'};
  if (pending) return {kind:'busy'};
  if (containsPrivateDetails(trimmed)) {
    addMessage('[Personal details removed]','user');
    addMessage('Please don’t enter your TFN, passport number, contact details, myGov password or other personal details here. Use the linked government service directly.');
    input.value='';
    return {kind:'privacy'};
  }
  if (/^(main menu|start over|new chat|go back)$/i.test(trimmed)) {
    resetChat();
    return {kind:'menu'};
  }
  ensureSession(trimmed);
  addMessage(trimmed,'user');
  input.value='';
  pending=true;
  sendButton.disabled=true;
  status.textContent='Searching indexed source notes…';
  try {
    const response=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:trimmed,topic}),
    });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    const answer=await response.json();
    const links=Array.isArray(answer.sources) ? answer.sources.map(safeLink).filter(Boolean) : [];
    const displayMode=answer.mode==='extractive' && Array.isArray(answer.evidence) && answer.evidence.length===0 ? 'abstain' : answer.mode;
    const diagnostics=answer.diagnostics && typeof answer.diagnostics==='object' ? answer.diagnostics : {};
    const evidence=Array.isArray(answer.evidence) ? answer.evidence.map(item=>({title:item.title,agency:item.agency,url:item.url,reviewed_on:item.reviewed_on})) : [];
    const details=displayMode==='guidance' ? null : {retrieved:diagnostics.retrieved,reason:diagnostics.reason,generation:diagnostics.generation,evidence};
    addMessage(String(answer.text||'No answer was returned.'),'assistant',links,Array.isArray(answer.steps)?answer.steps:[],true,displayMode,details);
    return answer;
  } catch {
    addMessage('The local service is unavailable. Please try again after the backend starts.','assistant');
    return {kind:'error'};
  } finally {
    pending=false;
    sendButton.disabled=false;
    status.textContent='';
    input.focus();
  }
}

function resetChat() {
  historyState.activeId=null;
  currentMessages=[];
  persistHistory();
  messages.replaceChildren();
  setTopic('tax');
  addMessage('G’day. I can help you find information about Australian tax or visas. What would you like to know?');
  showStarterQuestions();
  input.value='';
  input.focus();
}

form.addEventListener('submit',event=>{event.preventDefault();void send(input.value)});
suggestionsEl.addEventListener('click',event=>{const button=event.target.closest('button[data-question]');if(button)void send(button.dataset.question)});
messages.addEventListener('click',event=>{
  const button=event.target.closest('#empty-state button[data-question]');
  if (!button) return;
  setTopic(button.dataset.topic);
  void send(button.dataset.question);
});
topicButtons.forEach(button=>button.addEventListener('click',()=>{setTopic(button.dataset.topic,true);input.focus()}));
document.getElementById('new-chat').addEventListener('click',resetChat);
document.getElementById('history-open').addEventListener('click',()=>{renderHistory();historyDialog.showModal()});
document.getElementById('history-close').addEventListener('click',()=>historyDialog.close());
historyDialog.addEventListener('click',event=>{if(event.target===historyDialog)historyDialog.close()});
document.getElementById('sources-open').addEventListener('click',()=>sourcesDialog.showModal());
document.getElementById('sources-close').addEventListener('click',()=>sourcesDialog.close());
sourcesDialog.addEventListener('click',event=>{if(event.target===sourcesDialog)sourcesDialog.close()});
sourceFilterButtons.forEach(button=>button.addEventListener('click',()=>{sourceFilter=button.dataset.sourceTopic;renderSourceList()}));
historyList.addEventListener('click',event=>{
  const deleteButton=event.target.closest('button[data-delete-id]');
  if (deleteButton) {deleteSession(deleteButton.dataset.deleteId);return}
  const entry=event.target.closest('button[data-id]');
  if (entry) restoreSession(entry.dataset.id);
});
historyClear.addEventListener('click',()=>{
  if (!historyState.sessions.length) return;
  if (!window.confirm('Delete all chats saved in this browser?')) return;
  historyState.sessions=[];
  resetChat();
  renderHistory();
  historyDialog.close();
});

if (historyState.activeId) restoreSession(historyState.activeId);
else resetChat();
void loadSiteInfo();
