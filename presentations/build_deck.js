const pptxgen = require('pptxgenjs');
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';                 // 13.3 x 7.5
pres.author = 'Haydn Stucker';
pres.title  = 'EV Production and Ancillary Investment';

const INK='14211F', MUT='5F706D', WHT='FFFFFF', DARK='0B3B38', DARK2='11504B';
const TEAL='0D9488', ORNG='D94F04', VIOL='7048C4', LINE='DCE4E2';
const HEAD='Cambria', BODY='Calibri';
const W=13.33, H=7.5;

const chartBase = () => ({
  showLegend:false, showTitle:false,
  catAxisLabelColor:MUT, valAxisLabelColor:MUT,
  catAxisLabelFontFace:BODY, valAxisLabelFontFace:BODY,
  catAxisLabelFontSize:11, valAxisLabelFontSize:11,
  valGridLine:{color:LINE,size:1}, catGridLine:{style:'none'},
  catAxisLineShow:false, valAxisLineShow:false,
});

function titleBar(s, kicker, title){
  s.addText(kicker, {x:0.7,y:0.5,w:11.9,h:0.28,fontSize:12,bold:true,color:TEAL,
    charSpacing:1.6,fontFace:BODY,isTextBox:true,margin:0});
  s.addText(title, {x:0.7,y:0.82,w:11.9,h:0.72,fontSize:36,bold:true,color:INK,
    fontFace:HEAD,isTextBox:true,margin:0});
}
function statCard(s,x,y,w,h,val,label,color){
  s.addShape(pres.ShapeType.roundRect,{x,y,w,h,fill:{color:'F4F8F7'},
    rectRadius:0.08,line:{color:'FFFFFF',width:0}});
  s.addText(val,{x:x+0.03,y:y+0.14,w:w-0.06,h:0.62,fontSize:32,bold:true,color,
    align:'center',fontFace:HEAD,isTextBox:true,margin:0});
  s.addText(label,{x:x+0.10,y:y+0.78,w:w-0.20,h:0.72,fontSize:10.5,color:MUT,
    align:'center',fontFace:BODY,isTextBox:true,margin:0});
}

/* ---------- 1 TITLE ---------- */
{
  const s=pres.addSlide(); s.background={color:DARK};
  s.addShape(pres.ShapeType.ellipse,{x:10.3,y:-1.5,w:5.2,h:5.2,fill:{color:DARK2},line:{width:0}});
  s.addShape(pres.ShapeType.ellipse,{x:11.9,y:4.9,w:3.0,h:3.0,fill:{color:DARK2},line:{width:0}});
  s.addText('AIPI 590 · ALTERNATIVE DATA · PROJECT UPDATE',
    {x:0.9,y:1.5,w:10,h:0.3,fontSize:12,bold:true,color:'6FD8CB',charSpacing:1.8,
     fontFace:BODY,isTextBox:true,margin:0});
  s.addText('EV production and\nancillary investment',
    {x:0.9,y:2.0,w:9.6,h:1.9,fontSize:46,bold:true,color:WHT,lineSpacing:52,
     fontFace:HEAD,isTextBox:true,margin:0});
  s.addText('Does national growth in EV production predict new automotive-sector manufacturing-investment announcements?',
    {x:0.9,y:4.05,w:8.8,h:0.9,fontSize:16,color:'BFD9D5',italic:true,
     fontFace:BODY,isTextBox:true,margin:0});
  s.addText('Haydn Stucker  ·  Duke Pratt School of Engineering  ·  Data: Thurro connector (India)',
    {x:0.9,y:6.4,w:11,h:0.3,fontSize:12,color:'8FB4AF',fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 30 seconds here \u2014 set the frame and move on\n\u2022 Question: does national EV production growth lead investment announcements\n\u2022 Alt-data angle: production as an early signal of where capital gets committed\n\u2022 Two parts: national (primary), state siting (stretch)\n\u2022 All data via the Thurro connector, India only");
}

/* ---------- 2 PROBLEM ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'01 · THE PROBLEM','What we are actually testing');
  s.addText('When more EVs roll off assembly lines nationally, is that a signal that automakers are about to commit capital to new plants — and does the same pattern predict which states land it?',
    {x:0.7,y:1.6,w:11.9,h:0.6,fontSize:15,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});

  const rows=[
    {n:'PRIMARY',w:'~80% of effort',c:TEAL,
     t:'National EV production growth leads investment announcements',
     d:'X = monthly national EV production growth.  Y = count and value of new manufacturing-investment announcements.  A lead–lag test: does X move first?'},
    {n:'STRETCH',w:'~20% of effort',c:VIOL,
     t:'State EV demand concentration explains where investment is sited',
     d:'Does a state\'s share of EV demand predict its share of announced capacity — or do incentives decide siting instead, as the IRA gigafactory wave suggests?'},
  ];
  let y=2.45;
  rows.forEach(r=>{
    s.addShape(pres.ShapeType.roundRect,{x:0.7,y,w:11.9,h:1.75,fill:{color:'F4F8F7'},
      rectRadius:0.08,line:{width:0}});
    s.addShape(pres.ShapeType.ellipse,{x:1.0,y:y+0.28,w:0.42,h:0.42,fill:{color:r.c},line:{width:0}});
    s.addText(r.n,{x:1.6,y:y+0.26,w:2.2,h:0.3,fontSize:11,bold:true,color:r.c,
      charSpacing:1.4,fontFace:BODY,isTextBox:true,margin:0});
    s.addText(r.w,{x:10.3,y:y+0.26,w:2.0,h:0.3,fontSize:11,color:MUT,align:'right',
      fontFace:BODY,isTextBox:true,margin:0});
    s.addText(r.t,{x:1.6,y:y+0.56,w:10.6,h:0.36,fontSize:19,bold:true,color:INK,
      fontFace:HEAD,isTextBox:true,margin:0});
    s.addText(r.d,{x:1.6,y:y+0.97,w:10.6,h:0.66,fontSize:13,color:MUT,
      fontFace:BODY,isTextBox:true,margin:0});
    y+=2.0;
  });
  s.addText('The primary question is national and stands alone. Siting is an extension, not a requirement.',
    {x:0.7,y:6.6,w:11.9,h:0.3,fontSize:12,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Say explicitly that the primary question is gradeable on its own\n\u2022 X = monthly national EV production growth\n\u2022 Y = count and value of new manufacturing-investment announcements\n\u2022 The test is lead-lag: does X move first, and at what lag\n\u2022 Stretch: does a state's demand share predict its share of announced capacity\n\u2022 Honest caveat: siting may be incentive-driven, as the US IRA wave suggests\n\u2022 So the project does not fail if the stretch answer is that incentives decide");
}

/* ---------- 3 DATASETS ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'02 · TARGET DATASETS','Four named on the brief. Three delivered.');

  const cards=[
    {t:'National production & sales',s:'DELIVERED',c:TEAL,
     d:'SIAM monthly production, domestic sales and exports by OEM and model.',
     m:'40 usable months · 2023-04 → 2026-07'},
    {t:'State-level registrations',s:'DELIVERED',c:TEAL,
     d:'VAHAN registrations by state, segment and maker. Reconciles exactly to the national file.',
     m:'3,216 rows · 36 states · 2018-01 → 2026-08'},
    {t:'EV pricing & specs',s:'DELIVERED',c:TEAL,
     d:'Weekly model-level prices, battery capacity and range for cars and two-wheelers.',
     m:'654 variants · 2025-11 → 2026-09'},
    {t:'Industrial investment tracking',s:'NO USABLE DATA',c:ORNG,
     d:'Intended source of the dependent variable. Contains no EV content — see backup slide.',
     m:'Substitute: 34 hand-coded filing events'},
  ];
  let x=0.7;
  cards.forEach(c=>{
    s.addShape(pres.ShapeType.roundRect,{x,y:1.75,w:2.92,h:3.5,
      fill:{color:c.c===ORNG?'FDF1EC':'F4F8F7'},rectRadius:0.08,line:{width:0}});
    s.addShape(pres.ShapeType.ellipse,{x:x+0.28,y:2.05,w:0.34,h:0.34,fill:{color:c.c},line:{width:0}});
    s.addText(c.s,{x:x+0.72,y:2.06,w:2.0,h:0.3,fontSize:9,bold:true,color:c.c,
      charSpacing:1.2,fontFace:BODY,isTextBox:true,margin:0});
    s.addText(c.t,{x:x+0.28,y:2.55,w:2.36,h:0.8,fontSize:16,bold:true,color:INK,
      fontFace:HEAD,isTextBox:true,margin:0});
    s.addText(c.d,{x:x+0.28,y:3.42,w:2.36,h:1.2,fontSize:11.5,color:MUT,
      fontFace:BODY,isTextBox:true,margin:0});
    s.addText(c.m,{x:x+0.28,y:4.66,w:2.36,h:0.45,fontSize:10,bold:true,color:c.c,
      fontFace:BODY,isTextBox:true,margin:0});
    x+=3.05;
  });

  s.addText([
    {text:'The fourth dataset was meant to be the dependent variable. ',options:{bold:true,color:INK}},
    {text:'Its whole automotive sector is two rows, titled "Infra" and "Non NIP worklist rejection". 113 of its 115 energy-storage rows are oil, gas and LNG. Nothing in it matches any EV or battery keyword.',options:{color:MUT}},
  ],{x:0.7,y:5.55,w:11.9,h:0.8,fontSize:13,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Three of four datasets landed clean \u2014 do not dwell, 60 seconds max\n\u2022 Production: SIAM, 40 usable months, 2023-04 to 2026-07\n\u2022 Registrations: VAHAN, 3,216 state-month rows, reconciles exactly to the national file\n\u2022 Pricing: 654 variants, weekly from Nov 2025 \u2014 thinnest and least load-bearing\n\u2022 The fourth was meant to be the dependent variable and is unusable\n\u2022 Do not read the orange detail aloud \u2014 point at it, defer to the backup slide\n\u2022 Substitute: 34 events hand-coded from exchange filings");
}

/* ---------- 4 EDA A ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'03 · INITIAL EDA','The market is growing fast — and is mostly two-wheelers');

  s.addChart(pres.ChartType.line,[{
    name:'EV registrations',
    labels:['2018','2019','2020','2021','2022','2023','2024','2025'],
    values:[131197,167917,126007,341279,1059660,1581708,2025425,2356222],
  }],{...chartBase(),x:0.7,y:1.8,w:7.3,h:3.5,
      chartColors:[TEAL],lineSize:3,lineSmooth:false,
      showValue:false,valAxisMaxVal:2500000,
      valAxisLabelFormatCode:'#,##0,,"M"'});
  s.addText('Annual EV registrations, India (full years). 2026 is at 2.20M through August alone.',
    {x:0.7,y:5.35,w:7.3,h:0.5,fontSize:10.5,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});

  statCard(s,8.35,1.85,2.05,1.62,'62%','of 2026 EV volume\nis two-wheelers',TEAL);
  statCard(s,10.57,1.85,2.05,1.62,'27%','three-wheelers\n(largely e-rickshaw)',TEAL);
  statCard(s,8.35,3.66,2.05,1.62,'10%','four-wheelers —\nthe capex target segment',ORNG);
  statCard(s,10.57,3.66,2.05,1.62,'18×','registration growth\n2018 → 2025',TEAL);

  s.addText([
    {text:'Why this matters:  ',options:{bold:true,color:INK}},
    {text:'the volume is 2W/3W, but the investment announcements we care about are concentrated in 4W and cell manufacturing. The demand signal and the capex signal may not be measuring the same market.',options:{color:MUT}},
  ],{x:0.7,y:6.0,w:11.9,h:0.8,fontSize:13,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Lead with the growth, then immediately complicate it\n\u2022 Registrations grew about 18x from 2018 to 2025\n\u2022 Peak month was 332,544 in July 2026\n\u2022 But the mix is 62% two-wheelers, 27% three-wheelers, only 10% four-wheelers\n\u2022 The capex we care about is four-wheelers and cell manufacturing\n\u2022 So the demand signal and the capex signal may not track the same market\n\u2022 This is a real analytical risk, not a footnote");
}

/* ---------- 5 EDA B ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'03 · INITIAL EDA','Demand is concentrated; the production feed is catching up');

  s.addChart(pres.ChartType.bar,[{
    name:'Share of 2026 EV registrations',
    labels:['Uttar Pradesh','Maharashtra','Karnataka','Tamil Nadu','Madhya Pradesh','Rajasthan','West Bengal','Bihar'],
    values:[14.2,11.2,9.2,8.6,5.8,5.1,5.0,4.7],
  }],{...chartBase(),x:0.7,y:1.8,w:5.9,h:3.9,barDir:'bar',
      chartColors:[TEAL],barGapWidthPct:45,
      showValue:true,dataLabelPosition:'outEnd',dataLabelColor:MUT,
      dataLabelFontFace:BODY,dataLabelFontSize:10,dataLabelFormatCode:'0.0"%"',
      valAxisHidden:true,valGridLine:{style:'none'}});
  s.addText('Top-5 states take 49% of national EV registrations (HHI 0.071).',
    {x:0.7,y:5.75,w:5.9,h:0.4,fontSize:10.5,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});

  s.addChart(pres.ChartType.line,[{
    name:'Production as % of registrations',
    labels:['23Q2','23Q3','23Q4','24Q1','24Q2','24Q3','24Q4','25Q1','25Q2','25Q3','25Q4','26Q1','26Q2','26Q3'],
    values:[26.5,34.9,27.6,25.7,33.9,44.6,37.7,44.8,42.9,49.1,49.4,53.8,54.1,59.9],
  }],{...chartBase(),x:7.0,y:1.8,w:5.6,h:3.9,
      chartColors:[VIOL],lineSize:3,lineSmooth:false,
      valAxisMinVal:0,valAxisMaxVal:70,valAxisLabelFormatCode:'0"%"'});
  s.addText('Production coverage of registrations rose 27% → 60%. Four-wheeler EVs remain structurally under-captured.',
    {x:7.0,y:5.75,w:5.6,h:0.6,fontSize:10.5,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});

  s.addText([
    {text:'A first lead test on the proxy pair gives +0.24 at k=0, −0.20 at k=1, +0.40 at k=2. ',options:{bold:true,color:INK}},
    {text:'Sign-alternating at n=39 — the machinery runs, but this reads as noise, not structure.',options:{color:MUT}},
  ],{x:0.7,y:6.4,w:11.9,h:0.55,fontSize:13,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Two points: siting is a fair question, and the machinery is built\n\u2022 Top-5 states hold 49% of demand, HHI 0.071 \u2014 concentrated but not extreme\n\u2022 UP 14.2%, Maharashtra 11.2%, Karnataka 9.2%, Tamil Nadu 8.6%\n\u2022 Production coverage of registrations rose from 27% to 60%\n\u2022 Four-wheeler EVs still under-captured: ICE and EV share one nameplate in the feed\n\u2022 Lead test runs: +0.24 at k=0, -0.20 at k=1, +0.40 at k=2, n=39\n\u2022 Be honest \u2014 signs alternate, so that is noise, not a result");
}

/* ---------- 6 SUCCESS ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'04 · SUCCESS & EVALUATION','What counts as an answer — and can we detect one?');

  s.addShape(pres.ShapeType.roundRect,{x:0.7,y:1.8,w:4.2,h:4.35,
    fill:{color:'F4F8F7'},rectRadius:0.08,line:{width:0}});
  s.addShape(pres.ShapeType.ellipse,{x:1.0,y:2.08,w:0.3,h:0.3,fill:{color:TEAL},line:{width:0}});
  s.addText('Success is a defensible answer, not a positive one',
    {x:1.0,y:2.52,w:3.6,h:0.8,fontSize:16,bold:true,color:INK,fontFace:HEAD,isTextBox:true,margin:0});
  s.addText([
    'A clean "production does not lead announcements" is valid — but only if the test could have detected a lead.',
    'Poisson regression on monthly announcement counts, with lagged production growth.',
    'Baseline to beat: counts from their own lag plus a time trend.',
    'Placebo: shuffle announcement dates within year; the lead must vanish.',
  ].map((t,i,a)=>({text:t,options:{bullet:true,breakLine:i<a.length-1}})),
    {x:1.0,y:3.4,w:3.6,h:2.55,fontSize:12,color:MUT,fontFace:BODY,
     paraSpaceAfter:9,isTextBox:true,margin:0});

  const ev=['16','25','35','50','65','80','100','120'];
  s.addChart(pres.ChartType.line,[
    {name:'Large effect (RR 2.0)',   labels:ev,values:[54,80,93,99,100,100,100,100]},
    {name:'Moderate effect (RR 1.5)',labels:ev,values:[15,28,42,61,75,84,92,96]},
    {name:'Small effect (RR 1.25)',  labels:ev,values:[4,7,10,17,22,26,35,44]},
  ],{...chartBase(),x:5.15,y:1.8,w:7.47,h:3.15,
     chartColors:[TEAL,ORNG,VIOL],lineSize:3,lineSmooth:false,
     showLegend:true,legendPos:'b',legendColor:MUT,legendFontFace:BODY,legendFontSize:10,
     valAxisMinVal:0,valAxisMaxVal:100,valAxisLabelFormatCode:'0"%"'});
  s.addText('Simulated power vs number of dated events, scanning lags k = 1…6. We have 16.',
    {x:5.15,y:4.95,w:7.47,h:0.3,fontSize:10.5,color:MUT,italic:true,fontFace:BODY,isTextBox:true,margin:0});

  statCard(s,5.15,5.32,3.65,0.83,'~73 events','for 80% power scanning six lags',ORNG);
  statCard(s,8.97,5.32,3.65,0.83,'~48 events','if the lag is fixed in advance',TEAL);

  s.addText([
    {text:'At our 16 events a moderate effect is caught 15% of the time. ',options:{bold:true,color:INK}},
    {text:'Fixing the lag in advance cuts the events we need by a third — the cheapest win available.',options:{color:MUT}},
  ],{x:0.7,y:6.38,w:11.9,h:0.54,fontSize:13,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 This is the slide that earns credit \u2014 spend your time here\n\u2022 Success is a defensible answer, not a positive one\n\u2022 A clean null is valid only if the test could have detected a lead\n\u2022 Method: Poisson regression on monthly counts, lagged production growth\n\u2022 Baseline uses their own lag plus a time trend; placebo shuffles dates within year\n\u2022 The power study is done, not planned \u2014 that is the point to land\n\u2022 At our 16 events a moderate effect is caught just 15% of the time\n\u2022 80% power needs about 73 events scanning six lags, about 48 if the lag is fixed\n\u2022 Fixing the lag in advance is the cheapest win we have\n\u2022 Real data at 16 events: no significant lead at any k, best p = 0.11\n\u2022 Say it plainly \u2014 that is not evidence of no lead, it is an underpowered test\n\u2022 If asked: false-positive rate checks out at 1.5-2.5%, solver validated against statsmodels");
}

/* ---------- 7 ROADMAP ---------- */
{
  const s=pres.addSlide(); s.background={color:WHT};
  titleBar(s,'05 · ROADMAP','Next steps');

  const steps=[
    {n:'1',t:'Settle the inclusion rule',d:'Decide what counts as an "announcement" — board approval, press note, or commissioning. This drives the row count more than more searching does.',c:ORNG},
    {n:'2',t:'Scale to the power target',d:'Systematic sweep of the filings corpus under that rule. We need 45–75 dated events; we have 22 dated, 16 inside the production window.',c:ORNG},
    {n:'3',t:'Build the panel',d:'Join production growth, registrations and announcements on month; state panel for the siting extension.',c:TEAL},
    {n:'4',t:'Run the tests',d:'Lag pre-registered at k=3 rather than scanned, with the baseline and placebo checks. Achieved power beside every coefficient.',c:TEAL},
    {n:'5',t:'Write up',d:'Including the negative result on the investment source, which is a finding about alt-data coverage in its own right.',c:TEAL},
  ];
  let y=1.85;
  steps.forEach(st=>{
    s.addShape(pres.ShapeType.ellipse,{x:0.7,y:y+0.03,w:0.52,h:0.52,fill:{color:st.c},line:{width:0}});
    s.addText(st.n,{x:0.7,y:y+0.11,w:0.52,h:0.36,fontSize:16,bold:true,color:WHT,
      align:'center',fontFace:HEAD,isTextBox:true,margin:0});
    s.addText(st.t,{x:1.45,y:y+0.02,w:3.5,h:0.36,fontSize:16,bold:true,color:INK,
      fontFace:HEAD,isTextBox:true,margin:0});
    s.addText(st.d,{x:5.1,y:y+0.03,w:7.5,h:0.62,fontSize:12.5,color:MUT,
      fontFace:BODY,isTextBox:true,margin:0});
    y+=0.95;
  });
  s.addText('Steps 1 and 2 are the critical path. Everything downstream is blocked on how many dated events we can defensibly assemble.',
    {x:0.7,y:6.55,w:11.9,h:0.4,fontSize:12,color:ORNG,bold:true,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Steps 1 and 2 are the critical path \u2014 everything else waits on them\n\u2022 Step 1: settle what counts as an announcement (board approval, press note, commissioning)\n\u2022 Step 2: scale extraction toward 45-75 dated events\n\u2022 We are at 22 dated, 16 inside the production window\n\u2022 Step 3: build the month panel, plus the state panel for the stretch\n\u2022 Step 4: run the tests with the lag pre-registered at k=3\n\u2022 Step 5: write up, including the negative result on the investment source\n\u2022 Close on this: the modelling is not the risk, the dependent variable is");
}

/* ---------- 8 BACKUP ---------- */
{
  const s=pres.addSlide(); s.background={color:DARK};
  s.addShape(pres.ShapeType.ellipse,{x:11.6,y:-1.2,w:4.2,h:4.2,fill:{color:DARK2},line:{width:0}});
  s.addText('BACKUP · FOR DISCUSSION',{x:0.7,y:0.5,w:11.9,h:0.3,fontSize:12,bold:true,
    color:'F0A98A',charSpacing:1.6,fontFace:BODY,isTextBox:true,margin:0});
  s.addText('Problems we hit — and what we need from you',
    {x:0.7,y:0.84,w:11.9,h:0.62,fontSize:31,bold:true,color:WHT,fontFace:HEAD,isTextBox:true,margin:0});

  const probs=[
    {t:'The dependent variable does not exist in the structured data',
     d:'The industrial-investment source has 2 automotive rows ("Infra", "Non NIP worklist rejection"), 113 of 115 energy-storage rows are oil and gas, and every row shares one snapshot date — so it cannot form a time series regardless of content.'},
    {t:'The substitute is too thin to regress on',
     d:'34 events across 24 companies, hand-coded from filings. 22 carry a date better than a fiscal period, but only 16 land inside the 40-month production window — across 11 months. The power study says we need 45–75.'},
    {t:'Two silent data defects found during ingestion',
     d:'2026-08 production is incomplete (5 of 11 OEMs reported) and reads as an 88% collapse. The connector\'s row cap scales with row width, so a wider query silently returns fewer rows.'},
  ];
  let y=1.7;
  probs.forEach(p=>{
    s.addShape(pres.ShapeType.roundRect,{x:0.7,y,w:7.5,h:1.5,fill:{color:DARK2},
      rectRadius:0.06,line:{width:0}});
    s.addText(p.t,{x:1.0,y:y+0.16,w:6.9,h:0.32,fontSize:14.5,bold:true,color:'F0A98A',
      fontFace:HEAD,isTextBox:true,margin:0});
    s.addText(p.d,{x:1.0,y:y+0.53,w:6.9,h:0.85,fontSize:11.5,color:'C7DAD7',
      fontFace:BODY,isTextBox:true,margin:0});
    y+=1.66;
  });

  s.addShape(pres.ShapeType.roundRect,{x:8.55,y:1.7,w:4.07,h:4.5,
    fill:{color:'FFFFFF'},rectRadius:0.06,line:{width:0}});
  s.addText('QUESTIONS FOR STAKEHOLDERS',{x:8.85,y:1.98,w:3.5,h:0.3,fontSize:10.5,bold:true,
    color:ORNG,charSpacing:1.2,fontFace:BODY,isTextBox:true,margin:0});
  const qs=[
    'Is there an investment or capex feed we have not been pointed at — project-level, PLI/ACC allocations, or state MoUs?',
    'Would you accept exchange filings as the announcement source, and what should count as an "announcement"?',
    'Is the single-snapshot limitation on the project registry permanent, or is a historical series retrievable?',
    'If the dated-event count stays well short of 45–75, do you prefer an underpowered national test or a pivot to the state panel?',
  ];
  s.addText(qs.map((t,i)=>({text:t,options:{bullet:true,breakLine:i<qs.length-1}})),
    {x:8.85,y:2.43,w:3.5,h:3.6,fontSize:12,color:INK,fontFace:BODY,
     paraSpaceAfter:11,isTextBox:true,margin:0});

  s.addText('None of this blocks the stretch question — the state panel has 3,216 clean rows and reconciles exactly.',
    {x:0.7,y:6.5,w:11.9,h:0.4,fontSize:12,color:'8FB4AF',italic:true,fontFace:BODY,isTextBox:true,margin:0});
  s.addNotes("\u2022 Only pull this up if asked, or if time allows\n\u2022 Problem 1: the dependent variable does not exist in the structured source\n\u2022 Problem 2: the substitute is thin \u2014 16 usable events against a 45-75 target\n\u2022 Problem 3: two silent data defects found during ingestion\n\u2022 The four questions are the real ask\n\u2022 Q2 (the inclusion rule) unblocks the most work \u2014 push for an answer on that\n\u2022 Q1 (a better capex feed) is highest value if the answer is yes\n\u2022 Fallback if events stay well short of 45-75: pre-register the lag, or pivot to the state panel");
}

pres.writeFile({fileName:'/Users/haydn/projects/duke/aipi-courses/aipi-590-ad/thurro-term-project/presentations/ev-investment-update.pptx'})
  .then(f=>console.log('written:',f));
