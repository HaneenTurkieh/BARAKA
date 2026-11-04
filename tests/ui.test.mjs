import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {JSDOM} from 'jsdom';
import {seed,validateState} from '../public/engine.js';
const dom=new JSDOM(await fs.readFile(new URL('../public/index.html',import.meta.url),'utf8'),{url:'https://baraka.example/'});
const {window}=dom;for(const key of ['window','document','location','localStorage','FormData'])globalThis[key]=window[key];
window.scrollTo=()=>{};window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};
const writes=[];globalThis.fetch=async(_url,options)=>{if(options?.method==='PUT'){const data=JSON.parse(options.body);assert.equal(validateState(data),true);writes.push(data);return {ok:true,json:async()=>({ok:true})};}return {ok:true,json:async()=>({state:seed()})};};
await import('../public/app.js');
const settle=()=>new Promise(resolve=>setTimeout(resolve,10));await settle();
const $=s=>document.querySelector(s),change=el=>el.dispatchEvent(new window.Event('change',{bubbles:true})),submit=f=>f.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
async function navigate(hash){location.hash=hash;await settle();}
test('all eight views render and navigation reflects the current route',async()=>{for(const route of ['overview','inventory','decisions','forecast','partners','market','impact','about']){await navigate(route);assert.ok($('h1')?.textContent.length>5);assert.ok(!$('#main').textContent.includes('undefined'));assert.ok(!$('#main').textContent.includes('NaN'));}});
test('inventory adds and edits a batch, filters it and deletes it',async()=>{
 await navigate('inventory');$('[data-action=add]').click();const f=$('#batch-form');f.elements.name.value='دفعة اختبار';f.elements.kg.value=7;f.elements.safe.checked=true;submit(f);assert.ok($('#batch-results').textContent.includes('دفعة اختبار'));
 $('#batch-search').value='دفعة اختبار';$('#batch-search').dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(document.querySelectorAll('tbody tr').length,1);
 $('[data-action=edit]').click();$('#batch-form').elements.kg.value=9;submit($('#batch-form'));assert.ok($('#batch-results').textContent.includes('9'));
 $('[data-action=delete]').click();$('[data-action=delete-confirm]').click();assert.ok(!$('#batch-results').textContent.includes('دفعة اختبار'));await settle();assert.ok(writes.length>=3);
});
test('scenario and forecast controls update computed results',async()=>{await navigate('decisions');const toggle=$('[data-scenario=transport]');toggle.checked=true;change(toggle);assert.ok($('#main').textContent.includes('43 كغم غير مخصصة'));await navigate('forecast');const select=$('[data-forecast=weather]'),before=$('.forecast-number').textContent;select.value='rain';change(select);assert.notEqual($('.forecast-number').textContent,before);});
test('market reservation can be created and cancelled',async()=>{await navigate('market');$('[data-action=reserve]').click();submit($('#reserve-form'));assert.equal(document.querySelectorAll('[data-action=cancel-reservation]').length,1);$('[data-action=cancel-reservation]').click();assert.equal(document.querySelectorAll('[data-action=cancel-reservation]').length,0);});
test('partner capacity changes persist and potentially hostile organization names are escaped',async()=>{await navigate('partners');const f=$('form[data-capacity]');f.elements.capacity.value=5;submit(f);assert.equal($('form[data-capacity]').elements.capacity.value,'5');$('#profile').click();$('#settings-form').elements.organization.value='<img src=x onerror=alert(1)>';submit($('#settings-form'));assert.equal($('#org-label img'),null);assert.ok($('#org-label').textContent.includes('<img'));await settle();});
