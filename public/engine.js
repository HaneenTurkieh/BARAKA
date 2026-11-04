export const seed = () => ({
  organization:'مطبخ الزيتون', city:'نابلس',
  batches:[
    {id:'B-104',name:'أرز بالخضار',category:'وجبات مطبوخة',kg:24,price:18,hours:4,safe:true,cold:true},
    {id:'B-105',name:'خبز طازج',category:'مخبوزات',kg:18,price:8,hours:8,safe:true,cold:false},
    {id:'B-106',name:'سلطة موسمية',category:'خضار وفواكه',kg:12,price:14,hours:2,safe:true,cold:true},
    {id:'B-107',name:'بقايا تحضير الخضار',category:'مخلفات عضوية',kg:9,price:0,hours:12,safe:false,cold:false},
    {id:'B-108',name:'معجنات الزعتر',category:'مخبوزات',kg:15,price:12,hours:6,safe:true,cold:false}
  ],
  destinations:[
    {id:'sale',name:'سوق بَرَكة',type:'sale',capacity:28,km:2,minutes:25,active:true,cold:true},
    {id:'charity',name:'مطبخ المجتمع · جهة افتراضية',type:'donation',capacity:30,km:4,minutes:40,active:true,cold:true},
    {id:'campus',name:'كافتيريا الجامعة · جهة افتراضية',type:'redistribution',capacity:15,km:6,minutes:55,active:true,cold:false},
    {id:'compost',name:'وحدة التسميد · جهة افتراضية',type:'compost',capacity:40,km:8,minutes:70,active:true,cold:false},
    {id:'energy',name:'وحدة الطاقة · جهة افتراضية',type:'energy',capacity:25,km:12,minutes:95,active:true,cold:false}
  ], reservations:[], history:[105,112,108,120,135,128,116], scenario:{recipient:false,transport:false,demand:false}
});
export const human = ['sale','donation','redistribution'];
export const labels={sale:'بيع مخفّض',donation:'تبرع',redistribution:'إعادة توزيع',compost:'تسميد عضوي',energy:'استرداد طاقة',disposal:'غير مخصص'};
export function allocate(state, baseline=false){
 const ds=state.destinations.map(d=>({...d,remaining:!d.active||(state.scenario.recipient&&d.id==='charity')?0:d.capacity*(state.scenario.demand&&d.type==='sale'?.5:1)}));
 const rows=[];let transport=state.scenario.transport?35:Infinity;
 const batches=baseline?[...state.batches]:[...state.batches].sort((a,b)=>Number(b.safe)-Number(a.safe)||a.hours-b.hours);
 for(const b of batches){let left=b.kg;
  const eligible=ds.filter(d=>d.remaining>0&&d.minutes/60<b.hours&&(!human.includes(d.type)||(b.safe&&(!b.cold||d.cold))));
  if(!baseline)eligible.sort((a,c)=>(human.includes(a.type)?0:1)-(human.includes(c.type)?0:1)||a.km-c.km);
  for(const d of eligible){const kg=Math.min(left,d.remaining,transport);if(kg<=0)continue;
   rows.push({batchId:b.id,name:b.name,destination:d.name,type:d.type,kg,km:d.km,minutes:d.minutes,value:d.type==='sale'?kg*b.price*.5:0,reason:human.includes(d.type)?`معتمدة للاستهلاك${b.cold?' مع توفر النقل المبرد':''}؛ الوصول خلال ${d.minutes} دقيقة ضمن المهلة والسعة المتاحة.`:`مسار استرداد عضوي متاح؛ ${!b.safe?'الدفعة غير معتمدة للاستهلاك البشري':'سعة مسارات الاستهلاك البشري غير كافية'}.`});
   left-=kg;d.remaining-=kg;transport-=kg;if(left<=0)break;
  }
  if(left>0)rows.push({batchId:b.id,name:b.name,destination:'بانتظار حل تشغيلي',type:'disposal',kg:left,km:0,minutes:0,value:0,reason:b.hours<=0?'انتهت المهلة المحددة؛ يلزم تقييم مختص.':'لا توجد سعة أو وسيلة نقل مؤهلة ضمن المهلة؛ يلزم تدخل المسؤول.'});
 }
 const sum=(filter)=>rows.filter(filter).reduce((s,r)=>s+r.kg,0),total=state.batches.reduce((s,b)=>s+b.kg,0),rescued=sum(r=>human.includes(r.type)),recovered=sum(r=>r.type!=='disposal');
 const trips=new Map();for(const r of rows)if(r.type!=='disposal')trips.set(r.destination,r.km);
 const km=[...trips.values()].reduce((s,v)=>s+v*2,0);
 return {rows,total,rescued,recovered,unassigned:total-recovered,organic:recovered-rescued,value:rows.reduce((s,r)=>s+r.value,0),km,efficiency:recovered?km/recovered:0,rate:total?rescued/total*100:0};
}
export function forecast(history,{weather='normal',day='work',event='none'}={}){
 const avg=history.reduce((a,b)=>a+b,0)/history.length;
 const factors={weather:weather==='rain'?.82:weather==='hot'?.92:1,day:day==='holiday'?.72:day==='weekend'?1.12:1,event:event==='exam'?.85:event==='festival'?1.25:1};
 const predicted=Math.round(avg*factors.weather*factors.day*factors.event),recommended=Math.ceil(predicted*1.05);
 return {avg:Math.round(avg),predicted,recommended,lower:Math.floor(predicted*.85),upper:Math.ceil(predicted*1.15),factors,prevented:Math.max(0,145-recommended)};
}
export function validateState(s){
 if(!s||typeof s.organization!=='string'||s.organization.length>80||typeof s.city!=='string'||s.city.length>50||!Array.isArray(s.batches)||s.batches.length>100||!Array.isArray(s.destinations)||s.destinations.length>20||!Array.isArray(s.history)||s.history.length!==7||!s.history.every(n=>Number.isFinite(n)&&n>=0&&n<=10000)||!Array.isArray(s.reservations)||s.reservations.length>100||!s.scenario)return false;
 const num=(n,min,max)=>Number.isFinite(n)&&n>=min&&n<=max;
 return new Set(s.batches.map(b=>b.id)).size===s.batches.length&&s.batches.every(b=>typeof b.id==='string'&&b.id.length<80&&typeof b.name==='string'&&b.name.length>0&&b.name.length<=80&&typeof b.category==='string'&&b.category.length<=50&&num(b.kg,.1,10000)&&num(b.price,0,10000)&&num(b.hours,0,168)&&typeof b.safe==='boolean'&&typeof b.cold==='boolean')&&s.destinations.every(d=>typeof d.id==='string'&&typeof d.name==='string'&&d.name.length<=100&&Object.keys(labels).includes(d.type)&&d.type!=='disposal'&&num(d.capacity,0,10000)&&num(d.km,0,500)&&num(d.minutes,0,1440)&&typeof d.active==='boolean'&&typeof d.cold==='boolean')&&['recipient','transport','demand'].every(k=>typeof s.scenario[k]==='boolean')&&s.reservations.every(r=>typeof r.id==='string'&&typeof r.name==='string'&&r.name.length<=80&&num(r.kg,.1,10000));
}
