// Actual independent V8 JSON parser. Deliberately exposes permissive behavior.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const received = fs.readFileSync(0);
const raw = received.toString('utf8');
const receivedSha = crypto.createHash('sha256').update(received).digest('hex');
function visit(x) {
  if (typeof x === 'number' && !Number.isFinite(x)) return {nonfinite:String(x)};
  if (typeof x === 'number' && Number.isInteger(x) && !Number.isSafeInteger(x)) return {unsafe_integer_decimal:String(x)};
  if (typeof x === 'string' && !x.isWellFormed()) return {unpaired_surrogate:true};
  if (Array.isArray(x)) return x.map(visit);
  if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,visit(v)]));
  return x;
}
try {
  const v=JSON.parse(raw), n=visit(v);
  function canonical(x) {
    if (Array.isArray(x)) return x.map(canonical);
    if (x && typeof x==='object') return Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])]));
    return x;
  }
  // A bounded fixture comparison, not a universal JSON canonicalization scheme.
  const semantic_sha=crypto.createHash('sha256').update(JSON.stringify(canonical(v)),'utf8').digest('hex');
  process.stdout.write(JSON.stringify({accepted:true,node:process.version,received_bytes:received.length,received_sha256:receivedSha,
    bounded_canonical_sha256:semantic_sha,probe:n.memory?.data?.parser_probe??null,obligation_count:(v.obligations??[]).length,mission_id:v.mission_id}));
} catch (e) {
  process.stdout.write(JSON.stringify({accepted:false,node:process.version,received_bytes:received.length,received_sha256:receivedSha,error:e.name}));
}
