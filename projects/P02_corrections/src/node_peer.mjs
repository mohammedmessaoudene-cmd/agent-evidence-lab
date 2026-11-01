// Independent Node implementation of the restricted P02 research wire/profile.
// Uses built-in crypto, exact BigInt arithmetic, separate persisted state.
// The file store is a single-writer research peer, not a concurrent server.
// Public deterministic fixture keys are NOT production credentials.
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

const LIMIT = 9007199254740991n;
function fail(s) { throw new Error(s); }
function integer(x) { if (!Number.isSafeInteger(x)) fail('not safe integer'); return x; }
function canonical(x, depth=0) {
  if (depth > 40) fail('excessive nesting');
  if (x === null || typeof x === 'boolean') return JSON.stringify(x);
  if (typeof x === 'number') { integer(x); return JSON.stringify(x); }
  if (typeof x === 'string') { if ([...x].some(c => c.charCodeAt(0)>127)) fail('ASCII only'); return JSON.stringify(x).replace(/\x7f/g,'\\u007f'); }
  if (Array.isArray(x)) return '['+x.map(v=>canonical(v,depth+1)).join(',')+']';
  if (x && typeof x === 'object') return '{'+Object.keys(x).sort().map(k=>canonical(k,depth+1)+':'+canonical(x[k],depth+1)).join(',')+'}';
  fail('unsupported wire type');
}
// JSON.parse alone silently overwrites duplicate keys. This parser rejects them,
// fractional/exponent tokens, excessive depth, trailing data and duplicate names.
function strictParse(text) {
  let i=0;
  function ws(){ while (/[ \t\r\n]/.test(text[i]||'x')) i++; }
  function str(){ const start=i++; let esc=false;
    while(i<text.length){ const c=text[i++]; if(!esc && c==='"') return JSON.parse(text.slice(start,i));
      if(!esc && c==='\\') esc=true; else esc=false; }
    fail('unterminated string'); }
  function val(depth=0){ if(depth>40) fail('excessive nesting'); ws(); const c=text[i];
    if(c==='"') return str();
    if(c==='{'){ i++; const obj=Object.create(null),keys=new Set(); ws(); if(text[i]==='}') {i++;return obj;}
      while(true){ws();if(text[i]!=='"') fail('object key');const k=str(); if(keys.has(k)) fail('duplicate JSON key'); keys.add(k);ws();if(text[i++]!==':')fail('colon'); obj[k]=val(depth+1);ws();const sep=text[i++];if(sep==='}')return obj;if(sep!==',')fail('object separator');}}
    if(c==='['){i++;const arr=[];ws();if(text[i]===']'){i++;return arr;}while(true){arr.push(val(depth+1));ws();const sep=text[i++];if(sep===']')return arr;if(sep!==',')fail('array separator');}}
    for (const [lit,v] of [['true',true],['false',false],['null',null]]) if(text.slice(i,i+lit.length)===lit){i+=lit.length;return v;}
    const m=/^-?(?:0|[1-9][0-9]*)/.exec(text.slice(i));if(!m)fail('bad token');i+=m[0].length;if(/[.eE]/.test(text[i]||'x'))fail('noninteger token');return integer(Number(m[0])); }
  const result=val();ws();if(i!==text.length)fail('trailing input');canonical(result);return result;
}
const hash=x=>crypto.createHash('sha256').update(canonical(x)).digest('hex');
function key(name){ const seed=crypto.createHash('sha256').update('P02-INSECURE-TEST-KEY:'+name).digest(); return crypto.createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed]),format:'der',type:'pkcs8'}); }
function pubKey(hex){return crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),Buffer.from(hex,'hex')]),format:'der',type:'spki'});}
function sign(payload,signer){return {payload,signer,signature:crypto.sign(null,Buffer.from(canonical({payload,signer})),key(signer)).toString('hex')};}
function exactKeys(obj, keys) { return obj!==null && typeof obj==='object' && !Array.isArray(obj) && canonical(Object.keys(obj).sort())===canonical([...keys].sort()); }
function verify(e,registry){if(!exactKeys(e,['payload','signature','signer']))fail('envelope shape');if(typeof e.signer!=='string'||!Object.hasOwn(registry,e.signer))fail('unenrolled signer');
  if(!/^[0-9a-f]{128}$/.test(e.signature))fail('signature encoding');if(!crypto.verify(null,Buffer.from(canonical({payload:e.payload,signer:e.signer})),pubKey(registry[e.signer]),Buffer.from(e.signature,'hex')))fail('bad signature');return e.payload;}
function evaluate(f, state, target, tainted=Object.create(null)){
  const cache=new Map(),active=new Set();
  function calc(n){if(Object.hasOwn(state,n)){if(Object.hasOwn(tainted,n))fail('BLOCKED_CONFLICT');return {score:state[n].value,frontier:{[n]:{revision:state[n].revision,digest:state[n].digest}}};}
    if(cache.has(n))return cache.get(n);if(active.has(n))fail('BLOCKED_CYCLE');if(!Object.hasOwn(f.nodes,n))fail('UNKNOWN_MISSING_LINEAGE');active.add(n);
    const spec=f.nodes[n], inputs=spec.inputs.map(calc);if(!inputs.length)fail('empty transform');const vals=inputs.map(o=>BigInt(o.score));let total=vals.reduce((a,b)=>a+b,0n),out;
    if(spec.op==='identity'&&vals.length===1)out=vals[0];else if(spec.op==='sum')out=total;else if(spec.op==='mean'){const d=BigInt(vals.length);out=total>=0n?total/d:-((-total+d-1n)/d);}
    else if(spec.op==='min')out=vals.reduce((a,b)=>a<b?a:b);else if(spec.op==='max')out=vals.reduce((a,b)=>a>b?a:b);else fail('unknown operator');
    if(out>LIMIT||out< -LIMIT)fail('unsafe result');const frontier=Object.create(null);for(const input of inputs)Object.assign(frontier,input.frontier);
    active.delete(n);const result={score:Number(out),frontier};cache.set(n,result);return result;}
  return calc(target);
}
function initial(f){
  const state=Object.create(null),versions=Object.create(null);
  const ids=[...Object.keys(f.leaves),...Object.keys(f.nodes),...Object.keys(f.decisions)];if(new Set(ids).size!==ids.length)fail('identities overlap');
  for(const [leaf,v] of Object.entries(f.leaves)){integer(v.value);integer(v.revision);if(v.revision<0)fail('negative revision');const h=hash({leaf,revision:v.revision,value:v.value});state[leaf]={revision:v.revision,value:v.value,digest:h};versions[leaf+'|'+v.revision]=h;}
  for(const d of Object.values(f.decisions)){integer(d.threshold);if(d.policy!=='ge-v1')fail('unknown policy');}
  return {graph_digest:hash(f),state,events:Object.create(null),versions,tainted:Object.create(null),conflicts:[]};
}
let persistenceReceipt=null;
function persist(file,store){const tmp=file+'.tmp';fs.mkdirSync(path.dirname(file),{recursive:true});const fd=fs.openSync(tmp,'w',0o600);try{fs.writeFileSync(fd,canonical(store));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,file);let dir;try{dir=fs.openSync(path.dirname(file),'r');fs.fsyncSync(dir);persistenceReceipt={file_fsync:true,rename_completed:true,directory_fsync:'COMPLETED',power_loss_durability:'NOT_TESTED'};}catch(err){if(process.platform!=='win32'||err.code!=='EPERM')throw err;persistenceReceipt={file_fsync:true,rename_completed:true,directory_fsync:'UNSUPPORTED_EPERM_WIN32',power_loss_durability:'NOT_ESTABLISHED'};}finally{if(dir!==undefined)fs.closeSync(dir);}}
function main(req){
  if(req.command==='verify'){const p=verify(req.envelope,req.registry);return {accepted:true,payload:p};}
  if(req.command==='canonical')return {canonical:canonical(req.value),digest:hash(req.value)};
  const f=req.fixture;let store=req.store_path&&fs.existsSync(req.store_path)?strictParse(fs.readFileSync(req.store_path,'utf8')):initial(f);
  if(store.graph_digest!==hash(f))fail('graph epoch mismatch');
  // Old pre-review peer snapshots are intentionally not migrated silently:
  // they omitted initial-version history and conflict quarantine evidence.
  if(!Object.hasOwn(store,'tainted')||!Array.isArray(store.conflicts))fail('legacy peer state requires explicit rebuild');
  function quarantine(p, leaves, reason){
    for(const leaf of leaves)store.tainted[leaf]=reason;
    store.conflicts.push({event_id:p.id,issuer:p.issuer,leaves:[...leaves].sort(),reason,payload_digest:hash(p)});
    if(req.store_path)persist(req.store_path,store);
    fail(reason);
  }
  if(req.command==='apply'){
    const p=verify(req.envelope,req.registry);
    if(!exactKeys(p,['schema','id','issuer','changes'])||p.schema!=='p02-correction/0.1'||p.issuer!==req.envelope.signer)fail('correction schema/issuer');
    if(typeof p.id!=='string'||!p.id)fail('invalid correction identity');
    if(!Array.isArray(p.changes)||!p.changes.length)fail('empty correction');
    // Validate every change before interpreting collisions or mutating state.
    const seen=new Set();for(const c of p.changes){
      if(!exactKeys(c,['leaf','revision','value']))fail('invalid full-partition replacement');
      integer(c.revision);integer(c.value);
      if(typeof c.leaf!=='string'||c.revision<0||seen.has(c.leaf)||!Object.hasOwn(f.leaves,c.leaf)||f.leaves[c.leaf].issuer!==p.issuer)fail('unauthorized partition');
      seen.add(c.leaf);
    }
    if(Object.hasOwn(store.events,p.id)){
      const prior=store.events[p.id];
      if(prior.payload.issuer!==p.issuer)fail('cross-issuer event ID collision');
      if(prior.digest!==hash(p))quarantine(p,new Set([...seen,...prior.payload.changes.map(c=>c.leaf)]),'event equivocation');
      return {status:'DUPLICATE',state:store.state};
    }
    const updates=[];let advanced=false;
    for(const c of p.changes){
      const h=hash({leaf:c.leaf,revision:c.revision,value:c.value}),k=c.leaf+'|'+c.revision,old=store.state[c.leaf];
      if(Object.hasOwn(store.versions,k)&&store.versions[k]!==h)quarantine(p,new Set([c.leaf]),'revision conflict');
      updates.push({c,h,k,advance:c.revision>old.revision});
    }
    // All authority/schema/revision checks succeeded. Apply as one persisted unit.
    for(const {c,h,k,advance} of updates){store.versions[k]=h;if(advance){store.state[c.leaf]={revision:c.revision,value:c.value,digest:h};advanced=true;}}
    store.events[p.id]={digest:hash(p),payload:p};
    if(req.store_path)persist(req.store_path,store);return {status:advanced?'APPLIED':'SUPERSEDED',state:store.state};
  }
  if(req.command==='receipt'){
    const d=f.decisions[req.decision_id];if(!d)fail('unknown decision');if(d.policy!=='ge-v1')fail('unknown policy');
    const result=evaluate(f,store.state,d.node,store.tainted),p={schema:'p02-review/0.1',event_id:req.event_id,decision_id:req.decision_id,graph_digest:hash(f),cutoff:f.cutoff,policy_digest:hash(d),frontier:result.frontier,score:result.score,outcome:result.score>=d.threshold,review:'REEXAMINED'};
    return {envelope:sign(p,d.owner),store_persisted:Boolean(req.store_path)};
  }
  if(req.command==='evaluate'){const outputs=Object.create(null);for(const [name,d] of Object.entries(f.decisions)){const r=evaluate(f,req.state||store.state,d.node,store.tainted);outputs[name]={...r,outcome:r.score>=d.threshold};}return {outputs};}
  fail('unknown command');
}
try{const request=strictParse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify({...main(request),storage_durability:persistenceReceipt})+'\n');}
catch(e){process.stdout.write(JSON.stringify({accepted:false,error:e.message})+'\n');process.exitCode=2;}
