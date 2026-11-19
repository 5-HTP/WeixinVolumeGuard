'use strict';
let generation = -1;
let armed = false;
let cleaned = false;
let leaseUntil = 0;
let blocked = 0;
let passed = 0;
let entries = [];
let timer = null;
let agentError = null;
const now = new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('GetTickCount64'), 'uint64', []);
function ticks() { return now().toNumber(); }
function check(rc, label) { if (rc < 0) throw new Error(label + ':' + rc); }
function fn(object, slot, result, args) {
  return new NativeFunction(object.readPointer().add(slot * Process.pointerSize).readPointer(), result, args);
}
function release(object) { if (object && !object.isNull()) fn(object, 2, 'uint', ['pointer'])(object); }
function output() { const p = Memory.alloc(Process.pointerSize); p.writePointer(ptr(0)); return p; }
function normalized(path) { return path.replace(/\//g, '\\').toLowerCase(); }
function cleanup() {
  armed = false;
  leaseUntil = 0;
  cleaned = true;
  if (timer !== null) { clearInterval(timer); timer = null; }
  let failure = null;
  for (const entry of entries) {
    if (!entry.installed) continue;
    try { Interceptor.revert(entry.target); entry.installed = false; }
    catch (error) { failure = String(error); }
  }
  Interceptor.flush();
  if (failure) throw new Error(failure);
  return status();
}
function status() {
  return { generation, armed: armed && ticks() < leaseUntil, cleaned,
    targetCount: entries.filter(x => x.installed).length, blockedCount: blocked, passedCount: passed, error: agentError };
}
rpc.exports = {
  setup(config) {
    if (generation !== -1 || Process.arch !== 'x64') throw new Error('InvalidAgentStateOrArchitecture');
    generation = config.generation;
    const callerModule = Process.getModuleByName(config.moduleName);
    if (normalized(callerModule.path) !== normalized(config.modulePath) ||
        !callerModule.base.equals(ptr(config.moduleBase))) throw new Error('ModuleChanged');
    const rva = Number(config.returnRva);
    const expectedReturn = callerModule.base.add(rva);
    const callerRange = Process.findRangeByAddress(expectedReturn);
    if (!Number.isSafeInteger(rva) || rva < 0 || rva >= callerModule.size ||
        !callerRange || !callerRange.protection.includes('x')) throw new Error('InvalidCallerRva');
    const ole = Process.getModuleByName('ole32.dll');
    const init = new NativeFunction(ole.getExportByName('CoInitializeEx'), 'int', ['pointer','uint']);
    const uninit = new NativeFunction(ole.getExportByName('CoUninitialize'), 'void', []);
    const parseGuid = new NativeFunction(ole.getExportByName('CLSIDFromString'), 'int', ['pointer','pointer']);
    const create = new NativeFunction(ole.getExportByName('CoCreateInstance'), 'int', ['pointer','pointer','uint','pointer','pointer']);
    function guid(value) { const p = Memory.alloc(16); check(parseGuid(Memory.allocUtf16String(value), p), 'Guid'); return p; }
    let enumerator = ptr(0), collection = ptr(0);
    let initialized = false;
    const targets = new Map();
    try {
      const rc = init(ptr(0), 0);
      check(rc, 'CoInitializeEx'); initialized = true;
      const p = output();
      check(create(guid('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),ptr(0),23,
        guid('{A95664D2-9614-4F35-A746-DE8DB63617E6}'),p), 'CreateEnumerator');
      enumerator = p.readPointer();
      const list = output();
      check(fn(enumerator,3,'int',['pointer','int','uint','pointer'])(enumerator,0,1,list),'EnumAudioEndpoints');
      collection = list.readPointer();
      const count = Memory.alloc(4);
      check(fn(collection,3,'int',['pointer','pointer'])(collection,count),'GetCount');
      if (count.readU32() === 0) throw new Error('NoOutputDevice');
      for (let i=0; i<count.readU32(); i++) {
        let device=ptr(0), volume=ptr(0);
        try {
          const d=output(), v=output();
          check(fn(collection,4,'int',['pointer','uint','pointer'])(collection,i,d),'Item'); device=d.readPointer();
          check(fn(device,3,'int',['pointer','pointer','uint','pointer','pointer'])(device,
            guid('{5CDF2C82-841E-4546-9722-0CF74078229A}'),23,ptr(0),v),'Activate'); volume=v.readPointer();
          const target=volume.readPointer().add(7*Process.pointerSize).readPointer();
          const module=Process.findModuleByAddress(target), range=Process.findRangeByAddress(target);
          if (!module || module.name.toLowerCase()!=='audioses.dll' || !range || !range.protection.includes('x') ||
              normalized(module.path)!==normalized(config.systemDirectory+'\\audioses.dll'))
            throw new Error('AudioImplementationUnsupported');
          targets.set(target.toString(),target);
        } finally { release(volume); release(device); }
      }
    } finally { release(collection); release(enumerator); if(initialized) uninit(); }
    try {
      for (const target of targets.values()) {
        const original=new NativeFunction(target,'int',['pointer','float','pointer']);
        const callback=new NativeCallback(function(self,value,context) {
          let stop=false;
          try { stop=armed && !cleaned && ticks()<leaseUntil && this.returnAddress.equals(expectedReturn); }
          catch(error) { armed=false; leaseUntil=0; agentError=String(error); }
          if(stop) { blocked++; return 0; }
          passed++;
          return original(self,value,context);
        },'int',['pointer','float','pointer']);
        const entry={target,original,callback,installed:false}; entries.push(entry);
        Interceptor.replace(target,callback); entry.installed=true;
      }
      Interceptor.flush();
      timer=setInterval(function() { if(agentError || (armed && ticks()>=leaseUntil)) cleanup(); },1000);
      return status();
    } catch(error) { cleanup(); throw error; }
  },
  renew(value) {
    if(agentError || cleaned || value!==generation || entries.length===0) throw new Error('ExpiredOrWrongGeneration');
    leaseUntil=ticks()+5000; armed=true; return status();
  },
  status,
  cleanup
};
