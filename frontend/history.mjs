export const HISTORY_KEY = 'gov-assistant-v2-local-history-v1';
export const MAX_SESSIONS = 20;
export const MAX_MESSAGES = 60;

const allowedHosts = new Set([
  'www.ato.gov.au', 'ato.gov.au', 'my.gov.au',
  'immi.homeaffairs.gov.au', 'www.servicesaustralia.gov.au',
  'www.passports.gov.au', 'www.workforceaustralia.gov.au',
  'www.education.gov.au', 'minister.homeaffairs.gov.au',
  'newcastle.nsw.gov.au',
]);

export function safeLink(link) {
  if (!link || typeof link.label !== 'string' || typeof link.url !== 'string') return null;
  try {
    const url = new URL(link.url);
    if (url.protocol !== 'https:' || !allowedHosts.has(url.hostname)) return null;
    return {label:link.label.slice(0,120),url:url.href};
  } catch { return null; }
}

function safeMessage(message) {
  if (!message || !['user','assistant'].includes(message.role) || typeof message.text !== 'string') return null;
  const rawDetails=message.details;
  const details=rawDetails && typeof rawDetails==='object' ? {
    retrieved:Number.isInteger(rawDetails.retrieved) && rawDetails.retrieved>=0 ? rawDetails.retrieved : 0,
    reason:typeof rawDetails.reason==='string' ? rawDetails.reason.slice(0,80) : '',
    generation:typeof rawDetails.generation==='string' ? rawDetails.generation.slice(0,80) : '',
    evidence:Array.isArray(rawDetails.evidence) ? rawDetails.evidence.slice(0,5).map(item=>{
      if (!item || typeof item.title!=='string' || typeof item.agency!=='string') return null;
      const link=safeLink({label:item.title,url:item.url});
      return link ? {title:link.label,url:link.url,agency:item.agency.slice(0,80),reviewed_on:typeof item.reviewed_on==='string'?item.reviewed_on.slice(0,10):''} : null;
    }).filter(Boolean) : [],
  } : null;
  return {
    role:message.role,
    // Answers can exceed 1,500 characters. Preserve them in full on reload;
    // otherwise a saved answer can appear to stop in the middle of a word.
    text:message.role==='user' ? message.text.slice(0,500) : message.text,
    steps:Array.isArray(message.steps) ? message.steps.filter(x=>typeof x==='string').slice(0,5).map(x=>x.slice(0,500)) : [],
    links:Array.isArray(message.links) ? message.links.map(safeLink).filter(Boolean).slice(0,5) : [],
    mode:['ollama','extractive','abstain','guidance'].includes(message.mode)?message.mode:'',
    details,
    feedback:message.feedback==='up'||message.feedback==='down'?message.feedback:null,
  };
}

function safeTime(value) {
  return Number.isFinite(value) && value >= 0 && value <= 8.64e15 ? value : Date.now();
}

export function loadHistory(storage) {
  try {
    const raw = JSON.parse(storage.getItem(HISTORY_KEY) || 'null');
    if (raw?.version !== 1 || !Array.isArray(raw.sessions)) throw new Error('Unknown history format');
    const sessions = raw.sessions.slice(0,MAX_SESSIONS).map(session => {
      if (!session || typeof session.id!=='string' || typeof session.title!=='string' || !Array.isArray(session.messages)) return null;
      return {
        id:session.id.slice(0,100),
        title:session.title.slice(0,80),
        topic:session.topic==='visa'?'visa':'tax',
        createdAt:safeTime(session.createdAt),
        updatedAt:safeTime(session.updatedAt),
        messages:session.messages.slice(-MAX_MESSAGES).map(safeMessage).filter(Boolean),
      };
    }).filter(Boolean);
    return {sessions,activeId:sessions.some(s=>s.id===raw.activeId)?raw.activeId:null};
  } catch { return {sessions:[],activeId:null}; }
}

export function saveHistory(storage,state) {
  try {
    const payload = {version:1,sessions:state.sessions.slice(0,MAX_SESSIONS),activeId:state.activeId};
    storage.setItem(HISTORY_KEY,JSON.stringify(payload));
    return true;
  } catch { return false; }
}

export function newSessionId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
