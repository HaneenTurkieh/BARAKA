import test from 'node:test';
import assert from 'node:assert/strict';
import {seed,allocate,human,forecast,validateState} from '../public/engine.js';
test('default simulation conserves every batch and respects all destination constraints',()=>{
 const s=seed(),p=allocate(s);assert.equal(p.total,78);assert.equal(p.rescued,69);assert.equal(p.organic,9);assert.equal(p.unassigned,0);
 for(const b of s.batches){const rows=p.rows.filter(r=>r.batchId===b.id);assert.equal(rows.reduce((a,r)=>a+r.kg,0),b.kg);for(const r of rows){if(r.type==='disposal')continue;const d=s.destinations.find(d=>d.name===r.destination);assert.ok(d.minutes/60<b.hours);if(human.includes(r.type)){assert.ok(b.safe);if(b.cold)assert.ok(d.cold);}}}
 for(const d of s.destinations)assert.ok(p.rows.filter(r=>r.destination===d.name).reduce((a,r)=>a+r.kg,0)<=d.capacity);
});
test('all stress scenario combinations preserve quantity and transport capacity',()=>{
 for(let mask=0;mask<8;mask++){const s=seed();s.scenario={recipient:!!(mask&1),transport:!!(mask&2),demand:!!(mask&4)};for(const baseline of [false,true]){const p=allocate(s,baseline);assert.equal(p.rows.reduce((a,r)=>a+r.kg,0),p.total);if(s.scenario.transport)assert.ok(p.recovered<=35);if(s.scenario.recipient)assert.ok(!p.rows.some(r=>r.destination.includes('مطبخ المجتمع')));if(s.scenario.demand)assert.ok(p.rows.filter(r=>r.type==='sale').reduce((a,r)=>a+r.kg,0)<=14);}}
});
test('expired and unsafe batches never enter human consumption paths',()=>{const s=seed();s.batches=s.batches.map(b=>({...b,safe:false}));assert.equal(allocate(s).rescued,0);s.batches=s.batches.map(b=>({...b,hours:0}));assert.equal(allocate(s).unassigned,78);});
test('zero destination capacity and empty inventory are handled',()=>{const s=seed();s.destinations.forEach(d=>d.capacity=0);assert.equal(allocate(s).unassigned,78);s.batches=[];const p=allocate(s);assert.equal(p.rate,0);assert.equal(p.efficiency,0);});
test('forecast responds to weather, workdays and local events',()=>{const h=seed().history,f=forecast(h);assert.equal(f.predicted,118);assert.equal(f.recommended,124);assert.ok(forecast(h,{weather:'rain'}).predicted<f.predicted);assert.ok(forecast(h,{day:'holiday'}).predicted<f.predicted);assert.ok(forecast(h,{event:'festival'}).predicted>f.predicted);assert.equal(forecast(Array(7).fill(0)).predicted,0);});
test('state input validation rejects malformed and oversized data',()=>{assert.equal(validateState(seed()),true);for(const invalid of [null,{}, {...seed(),history:[]},{...seed(),organization:'a'.repeat(81)}])assert.equal(validateState(invalid),false);const s=seed();s.batches[0].kg=-5;assert.equal(validateState(s),false);});
