// Final presentation (12-minute slot): EV production and ancillary investment.
//
// A new deck, not an edit of ev-investment-update.pptx: status decks are kept as
// frozen snapshots so the project's progression can be compared side by side.
//
// Every number on these slides comes from a file in this repository; the source is
// named in each slide's speaker notes.
//
//   NODE_PATH=<folder holding pptxgenjs> node presentations/build_final_deck.js
//
// Needs pptxgenjs 3.x (and the jszip it ships with). Writes
// presentations/ev-investment-final.pptx next to this script.
const path = require('path');
const fs = require('fs');
const pptxgen = require('pptxgenjs');
const JSZip = require(require.resolve('jszip', { paths: [require.resolve('pptxgenjs')] }));

const OUT = path.join(__dirname, 'ev-investment-final.pptx');

/* ---------- theme ---------- */
// Same palette and type as the September status deck, so the two read as one series.
const HEX = {
  INK: '14211F', MUT: '5F706D', DARK: '0B3B38', DARK2: '11504B', TEAL: '0D9488',
  ORNG: 'D94F04', VIOL: '7048C4', LINE: 'DCE4E2', TINT: 'F4F8F7', LTEAL: '6FD8CB',
  ONDARK: 'BFD9D5', SOFT: '9AA9A6', PEACH: 'F0A98A', LILAC: 'C9B8F0', SHADE: 'D5EEEA',
};
const THEME = {
  name: 'EV Investment',
  headFontFace: 'Cambria',
  bodyFontFace: 'Calibri',
  colors: {
    dk1: HEX.INK, lt1: 'FFFFFF', dk2: HEX.DARK, lt2: HEX.TINT,
    accent1: HEX.TEAL, accent2: HEX.ORNG, accent3: HEX.VIOL, accent4: HEX.MUT,
    accent5: HEX.DARK2, accent6: HEX.LTEAL, hlink: HEX.TEAL, folHlink: HEX.VIOL,
  },
};

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5
pres.author = 'Colby, Xianyu, Keming, Haydn';
pres.title = 'EV production and ancillary investment: final presentation';
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const C = pres.SchemeColor;
const INK = C.text1, WHITE = C.background1, DARK = C.text2, TINT = C.background2;
const TEAL = C.accent1, ORNG = C.accent2, VIOL = C.accent3, MUT = C.accent4;
const DARK2 = C.accent5, LTEAL = C.accent6;
const HEAD = '+mj-lt'; // theme heading font, for big numbers set outside a title
const CHART_FONT = '+mn-lt';

/* ---------- layouts ---------- */
const FOOTER = 'EV production and ancillary investment  ·  AIPI 590  ·  Final presentation';

pres.defineSlideMaster({
  title: 'TITLE_DARK',
  background: { color: DARK },
  objects: [
    { ellipse: { x: 10.3, y: -1.5, w: 5.2, h: 5.2, fill: { color: DARK2 }, line: { type: 'none' } } },
    { ellipse: { x: 11.9, y: 4.9, w: 3.0, h: 3.0, fill: { color: DARK2 }, line: { type: 'none' } } },
    { placeholder: { options: { name: 'kicker', type: 'body', x: 0.9, y: 1.45, w: 10, h: 0.35,
      fontSize: 13, bold: true, color: LTEAL, charSpacing: 1.8, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', x: 0.9, y: 1.95, w: 9.6, h: 1.9,
      fontSize: 46, bold: true, color: WHITE, margin: 0, valign: 'top', align: 'left' }, text: '' } },
    { placeholder: { options: { name: 'subtitle', type: 'body', x: 0.9, y: 4.05, w: 8.8, h: 0.95,
      fontSize: 18, italic: true, color: HEX.ONDARK, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'byline', type: 'body', x: 0.9, y: 6.3, w: 11, h: 0.4,
      fontSize: 13, color: HEX.ONDARK, margin: 0, valign: 'top' }, text: '' } },
  ],
});

pres.defineSlideMaster({
  title: 'CONTENT',
  background: { color: WHITE },
  margin: [0.5, 0.7, 0.6, 0.7],
  objects: [
    { placeholder: { options: { name: 'kicker', type: 'body', x: 0.7, y: 0.45, w: 11.9, h: 0.3,
      fontSize: 12, bold: true, color: TEAL, charSpacing: 1.6, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', x: 0.7, y: 0.78, w: 11.9, h: 0.72,
      fontSize: 32, bold: true, color: INK, margin: 0, valign: 'top', align: 'left' }, text: '' } },
    { text: { text: FOOTER, options: { x: 0.7, y: 7.0, w: 9, h: 0.25, fontSize: 10, color: MUT, margin: 0 } } },
  ],
  slideNumber: { x: 12.1, y: 7.0, w: 0.5, h: 0.25, fontSize: 10, color: MUT, align: 'right', margin: 0 },
});

pres.defineSlideMaster({
  title: 'CLOSE_DARK',
  background: { color: DARK },
  margin: [0.5, 0.7, 0.6, 0.7],
  objects: [
    { ellipse: { x: 11.6, y: -1.2, w: 4.2, h: 4.2, fill: { color: DARK2 }, line: { type: 'none' } } },
    { placeholder: { options: { name: 'kicker', type: 'body', x: 0.7, y: 0.45, w: 11.9, h: 0.3,
      fontSize: 12, bold: true, color: LTEAL, charSpacing: 1.6, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', x: 0.7, y: 0.78, w: 11.9, h: 0.72,
      fontSize: 32, bold: true, color: WHITE, margin: 0, valign: 'top', align: 'left' }, text: '' } },
    { text: { text: FOOTER, options: { x: 0.7, y: 7.0, w: 9, h: 0.25, fontSize: 10, color: HEX.ONDARK, margin: 0 } } },
  ],
  slideNumber: { x: 12.1, y: 7.0, w: 0.5, h: 0.25, fontSize: 10, color: HEX.ONDARK, align: 'right', margin: 0 },
});

/* ---------- helpers ---------- */
function head(s, kicker, title) {
  s.addText(kicker, { placeholder: 'kicker' });
  s.addText(title, { placeholder: 'title' });
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: INK, valign: 'top' }, o));
}
function card(s, x, y, w, h, color = TINT, extra = {}) {
  s.addShape(pres.ShapeType.roundRect, Object.assign({ x, y, w, h, fill: { color }, rectRadius: 0.08,
    line: { type: 'none' } }, extra));
}
function dot(s, x, y, color, d = 0.3) {
  s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { type: 'none' } });
}
function label(s, text, x, y, w, color = TEAL) {
  txt(s, text, { x, y, w, h: 0.28, fontSize: 11, bold: true, color, charSpacing: 1.4 });
}
function chip(s, text, x, y, w, fill, color = INK) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.3, fill: { color: fill }, rectRadius: 0.15,
    line: { type: 'none' } });
  txt(s, text, { x, y, w, h: 0.3, fontSize: 9.5, bold: true, color, align: 'center', valign: 'middle',
    charSpacing: 1.0 });
}
function numberBadge(s, n, x, y, fill = TEAL, d = 0.5) {
  dot(s, x, y, fill, d);
  txt(s, String(n), { x, y: y + d * 0.17, w: d, h: d * 0.66, fontSize: 16, bold: true, color: WHITE,
    align: 'center', fontFace: HEAD });
}
function notes(s, lines) {
  s.addNotes(lines.map((l) => '• ' + l).join('\n'));
}
// Fresh option objects every call: pptxgenjs mutates option objects in place.
function chartBase(extra = {}) {
  return Object.assign({
    showTitle: false, showLegend: false,
    catAxisLabelColor: HEX.MUT, valAxisLabelColor: HEX.MUT,
    catAxisLabelFontFace: CHART_FONT, valAxisLabelFontFace: CHART_FONT,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 11,
    valGridLine: { color: HEX.LINE, size: 1 }, catGridLine: { style: 'none' },
    catAxisLineShow: false, valAxisLineShow: false,
    dataLabelFontFace: CHART_FONT, dataLabelFontSize: 11, dataLabelColor: HEX.INK,
    legendFontFace: CHART_FONT, legendFontSize: 11, legendColor: HEX.MUT,
  }, extra);
}

/* ======================================================================
   1  TITLE
   ====================================================================== */
pres.addSection({ title: 'Opening' });
{
  const s = pres.addSlide({ masterName: 'TITLE_DARK', sectionTitle: 'Opening' });
  s.addText('AIPI 590  ·  ALTERNATIVE DATA  ·  FINAL PRESENTATION', { placeholder: 'kicker' });
  s.addText('EV production and\nancillary investment', { placeholder: 'title' });
  s.addText('Does national growth in EV production predict new automotive-sector manufacturing-investment announcements?',
    { placeholder: 'subtitle' });
  s.addText('Colby, Xianyu, Keming, Haydn  ·  Duke Pratt School of Engineering  ·  Data: Thurro connector (India)',
    { placeholder: 'byline' });
  notes(s, [
    '~15 seconds. Set the frame and move on',
    'Same question as the September update; this time we have the answer',
    'Talk plan (~10:40 spoken, leaving time for handoffs): question and answer 1:00 · data and EDA 2:50 · models 4:40 · deliverable 0:55 · close 1:00',
    'Speakers not yet assigned: split by section (opening, data, models, deliverable and close)',
  ]);
}

/* ======================================================================
   2  QUESTION AND ANSWER UP FRONT
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Opening' });
  head(s, '01 · THE QUESTION AND THE ANSWER', 'What we asked, and what we found');

  card(s, 0.7, 1.8, 4.5, 4.8);
  label(s, 'WE ASKED', 1.0, 2.05, 3.9);
  dot(s, 1.0, 2.75, TEAL, 0.26);
  label(s, 'PRIMARY  ·  ~80% OF EFFORT', 1.4, 2.75, 3.6, TEAL);
  txt(s, 'Does national EV production growth lead automotive manufacturing-investment announcements?',
    { x: 1.0, y: 3.15, w: 3.9, h: 1.3, fontSize: 18, bold: true, fontFace: HEAD });
  dot(s, 1.0, 4.9, VIOL, 0.26);
  label(s, 'STRETCH  ·  ~20% OF EFFORT', 1.4, 4.9, 3.6, VIOL);
  txt(s, 'Does state EV demand explain where that investment is sited?',
    { x: 1.0, y: 5.3, w: 3.9, h: 1.0, fontSize: 18, bold: true, fontFace: HEAD });

  label(s, 'WE FOUND', 5.65, 1.85, 6.9);
  const rows = [
    { c: ORNG, t: 'Headline EV volume does not lead investment',
      d: 'Not announcements (lead-lag and Granger tests are null) and not spending (EV-exposed firms invest no faster than the rest).' },
    { c: TEAL, t: 'The mix of production does, tentatively',
      d: 'Export share and inventory build predict next month’s announcement: +34% Brier skill over the base rate, ahead of all 200 placebo copies.' },
    { c: VIOL, t: 'Siting tracks car demand and a state’s record',
      d: 'The announcing state is in our top five 64% of the time (AUC 0.85), though demand share and state size cannot be told apart.' },
  ];
  let y = 2.3;
  rows.forEach((r) => {
    dot(s, 5.65, y + 0.06, r.c, 0.3);
    txt(s, r.t, { x: 6.15, y, w: 6.45, h: 0.42, fontSize: 19, bold: true, fontFace: HEAD });
    txt(s, r.d, { x: 6.15, y: y + 0.47, w: 6.45, h: 0.8, fontSize: 14, color: MUT });
    y += 1.42;
  });
  txt(s, 'All three are served by our deliverable: a container that answers on request (slide 11).',
    { x: 5.65, y: 6.62, w: 6.95, h: 0.3, fontSize: 12, italic: true, color: MUT });

  notes(s, [
    '~60 seconds. Give the answer first, then spend the talk earning it',
    'Primary question, unchanged since the brief: does national EV production growth lead investment announcements',
    'Stretch: does state EV demand explain where the investment lands',
    'Finding 1, the direct answer: no. Headline volume leads neither what companies announce nor what they spend',
    'Finding 2: the composition of production does carry a signal: export share and unsold-inventory build. It is a lead, not a proven result; slide 8 says why',
    'Finding 3: siting follows car (4W) demand plus a state’s own record of announcements',
    'Sources: final-deliverable/model/exploratory-models-card.md, outlook-card.md, notebook-590/03_capex_panel_eda.ipynb',
  ]);
}

/* ======================================================================
   3  DATA
   ====================================================================== */
pres.addSection({ title: 'Data' });
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Data' });
  head(s, '02 · DATA', 'Four datasets, and a rebuilt dependent variable');

  label(s, 'THE FOUR THURRO DATASETS ON THE BRIEF', 0.7, 1.8, 6.3);
  const sets = [
    { n: 'National production & sales', d: 'SIAM, by OEM and model  ·  2023-04 → 2026-09  ·  42 months',
      st: 'MODELLED', fill: TEAL, fc: WHITE },
    { n: 'State-level registrations', d: 'VAHAN, 36 states by segment  ·  2018-01 → 2026-09  ·  reconciles to national',
      st: 'MODELLED', fill: TEAL, fc: WHITE },
    { n: 'EV pricing & specs', d: '654 car and 2W variants, weekly listings  ·  2025-11 → 2026-09',
      st: 'CONTEXT', fill: VIOL, fc: WHITE },
    { n: 'Industrial investment tracking', d: 'One snapshot; 2 automotive rows; 113 of 115 storage rows are oil and gas',
      st: 'NO EV CONTENT', fill: ORNG, fc: WHITE },
  ];
  let y = 2.2;
  sets.forEach((r) => {
    if (r.fill === ORNG) {
      s.addShape(pres.ShapeType.roundRect, { x: 0.7, y, w: 6.3, h: 1.0, fill: { color: ORNG, transparency: 91 },
        rectRadius: 0.08, line: { type: 'none' } });
    } else {
      card(s, 0.7, y, 6.3, 1.0);
    }
    txt(s, r.n, { x: 0.95, y: y + 0.14, w: 4.1, h: 0.34, fontSize: 16, bold: true, fontFace: HEAD });
    chip(s, r.st, 5.2, y + 0.15, 1.55, r.fill, r.fc);
    txt(s, r.d, { x: 0.95, y: y + 0.55, w: 5.85, h: 0.32, fontSize: 12.5, color: MUT });
    y += 1.12;
  });

  label(s, 'SO WE BUILT THE DEPENDENT VARIABLE OURSELVES', 7.4, 1.8, 5.3, ORNG);
  const dv = [
    { big: '34', unit: 'announcements', c: ORNG, ux: 8.85,
      d: 'Hand-coded from exchange filings, 2021-12 → 2026-09. What companies said they would build. The models predict these.' },
    { big: '182', unit: 'company-years of capex', c: TEAL, ux: 9.3,
      d: '52 named companies’ filed cash-flow statements, FY23–FY26. What they actually spent. Added after industry-partner feedback.' },
  ];
  y = 2.2;
  dv.forEach((r) => {
    card(s, 7.4, y, 5.23, 2.12);
    txt(s, r.big, { x: 7.7, y: y + 0.2, w: 1.5, h: 0.8, fontSize: 44, bold: true, color: r.c, fontFace: HEAD });
    txt(s, r.unit, { x: r.ux, y: y + 0.42, w: 3.2, h: 0.4, fontSize: 18, bold: true, fontFace: HEAD });
    txt(s, r.d, { x: 7.7, y: y + 1.1, w: 4.7, h: 0.9, fontSize: 13.5, color: MUT });
    y += 2.36;
  });

  notes(s, [
    '~55 seconds. Three of the four datasets on the brief were usable; point at the chips, do not read rows',
    'Production (SIAM) is the only true production series: 42 months, 2023-04 to 2026-09',
    'Registrations (VAHAN): state by segment back to 2018, reconciles exactly to the national total',
    'Pricing: weekly listings since Nov 2025, too short to model, used for context on the next slide',
    'The fourth dataset was meant to be the dependent variable and has no EV content, so we built our own two ways',
    'Announcements: 34 events hand-coded from exchange filings: what companies said',
    'Capex: after the industry-partner feedback in September we named 52 target companies and read their filed cash-flow statements: what they spent, 182 company-years',
    'Sources: data/README.md, data/manual/, data/processed/company_capex_annual.csv',
  ]);
}

/* ======================================================================
   4  THE MARKET (EDA)
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Data' });
  head(s, '03 · THE MARKET', 'EV demand grew 18×, and shifted toward cars');

  txt(s, 'Cars (4W) as a share of 2W + 3W + 4W EV registrations, %', { x: 0.7, y: 1.8, w: 6.6, h: 0.3,
    fontSize: 12, bold: true, color: MUT });
  s.addChart(pres.ChartType.bar, [{
    name: '4W share', labels: ['2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026*'],
    values: [0.9, 0.8, 2.8, 3.9, 3.4, 5.1, 4.8, 8.1, 9.9],
  }], chartBase({
    x: 0.6, y: 2.15, w: 6.8, h: 3.75, barDir: 'col', chartColors: [HEX.TEAL], barGapWidthPct: 45,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '0.0',
    valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 12, valGridLine: { style: 'none' },
  }));
  txt(s, '*2026 = January–September. Source: VAHAN registrations via Thurro.', { x: 0.7, y: 5.95, w: 6.6,
    h: 0.28, fontSize: 10.5, italic: true, color: MUT });

  const stats = [
    { v: '18×', l: 'EV registrations,\n2018 → 2025', c: TEAL },
    { v: '10%', l: 'of 2026 EV registrations\nare cars, double 2023–24', c: TEAL },
    { v: '+96%', l: 'car EV registrations,\nNov 2025 → Sep 2026', c: TEAL },
    { v: '+1.5%', l: 'same-model car prices\nover those months', c: ORNG },
  ];
  stats.forEach((st, i) => {
    const x = 7.75 + (i % 2) * 2.5, y = 1.85 + Math.floor(i / 2) * 2.08;
    card(s, x, y, 2.38, 1.9);
    txt(s, st.v, { x: x + 0.1, y: y + 0.22, w: 2.18, h: 0.72, fontSize: 36, bold: true, color: st.c,
      align: 'center', fontFace: HEAD });
    txt(s, st.l, { x: x + 0.12, y: y + 1.0, w: 2.14, h: 0.75, fontSize: 12.5, color: MUT, align: 'center' });
  });

  txt(s, [
    { text: 'Car demand doubled on ~15 new launches and longer range, not on price cuts. ', options: { bold: true } },
    { text: 'Cars are also where carmakers’ plant decisions are made, which matters on slide 9.', options: { color: MUT } },
  ], { x: 0.7, y: 6.35, w: 11.9, h: 0.5, fontSize: 14 });

  notes(s, [
    '~50 seconds. One message: the market grew fast, and the part that is changing is cars',
    'Registrations rose about 18x from 2018 to 2025; 2026 passed the 2025 total by September (peak month Sept 2026, ~335k)',
    'Volume is still two-wheelers (63% of 2026) and three-wheelers (27%); cars are 10%, up from ~5% in 2023–24',
    'From Nov 2025 to Sep 2026 car EV registrations nearly doubled while a same-model price index rose 1.5%; 142 of 152 price changes were rises',
    'What changed was supply: about 15 new models (e Vitara, Sierra EV, XEV 9S, Syros EV, Model Y) and median range up from 490 to ~520–540 km',
    'Why it matters: the capex we care about is cars and cells, and 4W share is what the siting model ends up using',
    'Sources: data/processed/ev_registrations_segment_monthly.csv, notebook-590/05_ev_prices.ipynb',
  ]);
}

/* ======================================================================
   5  CAPEX: WHAT COMPANIES SPENT
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Data' });
  head(s, '04 · WHAT COMPANIES SPENT', 'Capex followed the sector cycle, not EV volume');

  txt(s, 'Mean company capex growth by tier, % year on year', { x: 0.7, y: 1.8, w: 6.5, h: 0.3,
    fontSize: 12, bold: true, color: MUT });
  s.addChart(pres.ChartType.bar, [
    { name: 'ICE-led carmakers', labels: ['FY24', 'FY25', 'FY26'], values: [32.8, 37.7, 19.3] },
    { name: 'EV-led carmakers', labels: ['FY24', 'FY25', 'FY26'], values: [9.7, 37.6, 18.6] },
  ], chartBase({
    x: 0.6, y: 2.15, w: 6.7, h: 3.85, barDir: 'col', barGrouping: 'clustered', barGapWidthPct: 60,
    chartColors: [HEX.ORNG, HEX.TEAL], showValue: true, dataLabelPosition: 'outEnd',
    dataLabelFormatCode: '+0.0', valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 45,
    valGridLine: { style: 'none' }, showLegend: true, legendPos: 'b',
  }));

  const blocks = [
    { v: '+77%', c: TEAL, d: 'Sector capex, FY23 → FY26 (₹29.8k → ₹52.8k Cr, 36 firms), flat in the final year' },
    { v: '2.06 vs 2.08', c: ORNG, d: 'Capex intensity, EV-exposed vs other firms: no difference (t = −0.06, n = 35)' },
    { v: 'r = −0.37', c: ORNG, d: 'A firm’s own EV volume growth vs its next-period asset growth: wrong sign (n = 19)' },
  ];
  let y = 1.8;
  blocks.forEach((b) => {
    card(s, 7.7, y, 4.93, 1.32);
    txt(s, b.v, { x: 7.95, y: y + 0.14, w: 4.5, h: 0.52, fontSize: 26, bold: true, color: b.c, fontFace: HEAD });
    txt(s, b.d, { x: 7.95, y: y + 0.7, w: 4.5, h: 0.55, fontSize: 12.5, color: MUT });
    y += 1.45;
  });

  txt(s, [
    { text: 'Announcements came after the cycle: ', options: { bold: true } },
    { text: '25 of 34 fall in FY26–FY27, and announcing firms grew capex no faster that year (median +7.7% vs +20.5%).',
      options: { color: MUT } },
  ], { x: 0.7, y: 6.3, w: 11.9, h: 0.5, fontSize: 14 });

  notes(s, [
    '~65 seconds. This is the direct test of the hypothesis on the better dependent variable, and it is null',
    'Capex rose 77% over three years across the 36-firm panel, then flattened in FY26',
    'Chart: if EV volume drove plant spending, EV-led carmakers should out-invest ICE-led ones. The reverse: ICE-led grew faster in FY24 and matched them after',
    'Cross-sectional test, the well-powered one: capex intensity 2.06 for EV-exposed firms vs 2.08 for the rest, t = -0.06',
    'Within-company test (own EV volume vs own asset growth): r = -0.003 same period, -0.37 one period ahead. Wrong sign, small n, so treat it as uninformative rather than as proof of no effect',
    'A national-X design cannot be estimated at all: capex is annual, so there are only 2–3 usable period pairs',
    'An ICE-only control (Precision Camshafts) moves with the EV names, which points to a sector-wide cycle',
    'Announcements vs capex (notebook 04): spending ramped FY23→FY25, announcements surged in FY26–FY27 after it. Read capex as the cycle already seen, announcements as intent for the next one',
    'Sources: notebook-590/03_capex_panel_eda.ipynb, notebook-590/04_announcements_vs_capex.ipynb',
  ]);
}

/* ======================================================================
   6  EVALUATION DESIGN
   ====================================================================== */
pres.addSection({ title: 'Models' });
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Models' });
  head(s, '05 · HOW WE JUDGED A MODEL', 'Beat the base rate out of sample, then a placebo');

  const steps = [
    { t: 'Walk-forward test', d: 'Refit each month on the past only and score the month after. 19 test months, 8 of them followed by an announcement.' },
    { t: 'Beat the base rate', d: 'Brier skill against always forecasting the historical rate, with a bootstrap 90% interval on the gain.' },
    { t: 'Control for the cycle', d: 'ICE-vehicle production growth replaces the time trend, so EV features must add something beyond the sector cycle.' },
    { t: 'Survive a placebo', d: 'Shift the production columns by 200 random calendar offsets. A real lead should beat nearly all of them.' },
  ];
  steps.forEach((st, i) => {
    const x = 0.7 + i * 3.033;
    card(s, x, 1.85, 2.8, 2.85);
    numberBadge(s, i + 1, x + 0.25, 2.1);
    txt(s, st.t, { x: x + 0.25, y: 2.8, w: 2.35, h: 0.42, fontSize: 17, bold: true, fontFace: HEAD });
    txt(s, st.d, { x: x + 0.25, y: 3.28, w: 2.35, h: 1.35, fontSize: 14, color: MUT });
  });

  card(s, 0.7, 5.15, 7.4, 1.55);
  label(s, 'WHAT WE COMPARED, ON THE SAME SPLITS AND METRICS', 0.95, 5.35, 7.0);
  txt(s, [
    { text: 'National: ', options: { bold: true } }, { text: '7 models, base rate to gradient boosting.   ', options: { color: MUT } },
    { text: 'State: ', options: { bold: true } }, { text: '9 siting models.', options: { color: MUT, breakLine: true } },
    { text: 'Neural track: ', options: { bold: true } }, { text: 'MLP, GRU, LSTM, TCN, Transformer and N-BEATS.', options: { color: MUT } },
  ], { x: 0.95, y: 5.72, w: 7.0, h: 0.85, fontSize: 14, paraSpaceAfter: 4 });

  card(s, 8.35, 5.15, 4.28, 1.55, DARK);
  txt(s, 'FROM OUR SEPTEMBER CRITERIA', { x: 8.6, y: 5.33, w: 3.8, h: 0.3, fontSize: 11, bold: true,
    color: LTEAL, charSpacing: 1.2 });
  txt(s, '“Success is a defensible answer, not a positive one.”', { x: 8.6, y: 5.68, w: 3.85, h: 0.9,
    fontSize: 16, italic: true, color: WHITE, fontFace: HEAD });

  notes(s, [
    '~45 seconds. The protocol, so the next two slides can be read quickly',
    'Walk-forward with an expanding window: no month is ever scored by a model that saw it',
    'Brier skill is the improvement over a forecaster that always says the base rate; we report a bootstrap 90% interval, not just the point',
    'In September we planned a time-trend baseline. We replaced the trend with ICE-vehicle production growth, which tests the question directly: does EV information add anything beyond the sector cycle?',
    'Placebo: circularly shift the production columns 200 times. If shifted copies do as well, the "lead" is just a trend',
    'Everything, including the neural networks, ran on the same splits and metrics, so it all lands in one table (backup slide 14)',
    'Sources: final-deliverable/model/exploratory-models-card.md, exploration/evaluation.py',
  ]);
}

/* ======================================================================
   7  PRIMARY QUESTION: NATIONAL RESULT
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Models' });
  head(s, '06 · PRIMARY QUESTION', 'Composition, not volume, predicts announcements');

  txt(s, 'Brier skill over the base rate, %  ·  Logit L2, walk-forward, 19 test months', { x: 0.7, y: 1.8,
    w: 7.0, h: 0.3, fontSize: 12, bold: true, color: MUT });
  s.addChart(pres.ChartType.bar, [
    { name: 'Time-trend control', labels: ['Controls only', '+ EV production growth', '+ segment mix'], values: [5.8, 15.8, 33.1] },
    { name: 'ICE-production control', labels: ['Controls only', '+ EV production growth', '+ segment mix'], values: [-12.8, -0.2, 33.6] },
  ], chartBase({
    x: 0.6, y: 2.15, w: 7.2, h: 4.35, barDir: 'col', barGrouping: 'clustered', barGapWidthPct: 55,
    chartColors: [HEX.SOFT, HEX.TEAL], showValue: true, dataLabelPosition: 'outEnd',
    dataLabelFormatCode: '+0.0;−0.0', valAxisMinVal: -20, valAxisMaxVal: 40, valAxisMajorUnit: 10,
    valAxisLabelFormatCode: '0', showLegend: true, legendPos: 'b',
  }));

  card(s, 8.15, 1.8, 4.48, 1.75);
  txt(s, '+34%', { x: 8.4, y: 1.95, w: 1.9, h: 0.75, fontSize: 40, bold: true, color: TEAL, fontFace: HEAD });
  txt(s, 'Brier skill with segment mix\n(0.177 vs 0.266 for the base rate)', { x: 10.25, y: 2.05, w: 2.3, h: 0.7,
    fontSize: 12, color: MUT });
  txt(s, '90% interval of the gain [0.020, 0.164]  ·  AUC 0.84', { x: 8.4, y: 2.95, w: 4.1, h: 0.3,
    fontSize: 12.5, bold: true, color: INK });

  const pts = [
    { c: ORNG, t: 'Headline growth: no lead', d: 'No lead at 1–6 months (all p > 0.18); Granger p = 0.40–0.94; zero weight in the lasso.' },
    { c: TEAL, t: 'What carries it', d: 'Export share (+) and unsold-inventory build (−): the composition of production.' },
    { c: VIOL, t: 'A second model family agrees', d: 'An MLP picked the same feature set on its own: +34.1%, ahead of every placebo.' },
  ];
  let y = 3.8;
  pts.forEach((p) => {
    dot(s, 8.15, y + 0.05, p.c, 0.26);
    txt(s, p.t, { x: 8.55, y, w: 4.08, h: 0.34, fontSize: 15, bold: true, fontFace: HEAD });
    txt(s, p.d, { x: 8.55, y: y + 0.36, w: 4.08, h: 0.58, fontSize: 12.5, color: MUT });
    y += 0.98;
  });

  notes(s, [
    '~70 seconds. The core result. Walk the chart left to right',
    'Grey bars use the time-trend control, teal bars the ICE-production control',
    'Adding EV production growth looks useful with a trend (+15.8%), but with the ICE control it adds nothing (-0.2%). Headline growth was proxying the trend',
    'Adding the segment-mix block (export share, inventory build, 2W/3W growth, PV and 3W share) gives +33–34% under either control. Its interval clears zero',
    'In-sample tests agree: no lead from 1 to 6 months is significant; Granger is null both ways; the lasso gives production growth zero weight',
    'An MLP, built separately, chose the same feature set: +34.1% Brier skill, 0 of 200 placebos as good. Two model families agreeing is the strongest claim we can make',
    'This is the specification the container serves',
    'Sources: results/national/8_ice_control_ablation.csv, results/nn/summary.md, outlook-card.md',
  ]);
}

/* ======================================================================
   8  STRESS TEST
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Models' });
  head(s, '07 · IS IT REAL?', 'It beats every placebo, but rests on three months');

  // Number line: Brier score, lower is better. 0.15 .. 0.42 maps to x 0.95 .. 8.15.
  const X0 = 0.95, X1 = 8.15, V0 = 0.15, V1 = 0.42;
  const xv = (v) => X0 + (v - V0) / (V1 - V0) * (X1 - X0);
  label(s, 'PLACEBO  ·  BRIER SCORE, LOWER IS BETTER', 0.7, 1.8, 7.6);
  const LY = 2.72;
  s.addShape(pres.ShapeType.line, { x: X0, y: LY + 0.11, w: X1 - X0, h: 0, line: { color: HEX.LINE, width: 1 } });
  s.addShape(pres.ShapeType.roundRect, { x: xv(0.204), y: LY, w: xv(0.404) - xv(0.204), h: 0.22,
    fill: { color: HEX.LINE }, rectRadius: 0.11, line: { type: 'none' } });
  s.addShape(pres.ShapeType.roundRect, { x: xv(0.249), y: LY, w: xv(0.310) - xv(0.249), h: 0.22,
    fill: { color: HEX.SOFT }, rectRadius: 0.11, line: { type: 'none' } });
  s.addShape(pres.ShapeType.rect, { x: xv(0.279) - 0.02, y: LY - 0.06, w: 0.04, h: 0.34, fill: { color: INK },
    line: { type: 'none' } });
  dot(s, xv(0.177) - 0.15, LY - 0.04, TEAL, 0.3);
  txt(s, 'Real model\n0.177', { x: xv(0.177) - 0.6, y: LY - 0.62, w: 1.2, h: 0.5, fontSize: 11.5, bold: true,
    color: TEAL, align: 'center' });
  txt(s, '200 calendar-shifted copies:  best 0.204  ·  median 0.279', { x: xv(0.204), y: LY - 0.4, w: 5.2,
    h: 0.3, fontSize: 11.5, color: MUT });
  [0.15, 0.20, 0.25, 0.30, 0.35, 0.40].forEach((v) => {
    txt(s, v.toFixed(2), { x: xv(v) - 0.3, y: LY + 0.32, w: 0.6, h: 0.22, fontSize: 10, color: MUT, align: 'center' });
  });

  // Month by month: the model's probability against the base rate, with event months shaded.
  const months = ['Feb 25', 'Mar 25', 'Apr 25', 'May 25', 'Jun 25', 'Jul 25', 'Aug 25', 'Sep 25', 'Oct 25',
    'Nov 25', 'Dec 25', 'Jan 26', 'Feb 26', 'Mar 26', 'Apr 26', 'May 26', 'Jun 26', 'Jul 26', 'Aug 26'];
  const yv = [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1];
  const pm = [0.040, 0.010, 0.042, 0.152, 0.239, 0.054, 0.076, 0.010, 0.085, 0.157, 0.258, 0.193, 0.199,
    0.077, 0.345, 0.906, 0.783, 0.386, 0.768];
  const pb = [0.250, 0.235, 0.222, 0.211, 0.200, 0.190, 0.182, 0.174, 0.208, 0.200, 0.192, 0.185, 0.214,
    0.241, 0.233, 0.258, 0.281, 0.303, 0.324];
  label(s, 'WALK-FORWARD, MONTH BY MONTH  ·  P(ANNOUNCEMENT NEXT MONTH)', 0.7, 3.5, 7.6);
  s.addChart([
    { type: pres.ChartType.bar, data: [{ name: 'An announcement followed', labels: months, values: yv }],
      options: { chartColors: [HEX.SHADE], barGapWidthPct: 15 } },
    { type: pres.ChartType.line, data: [
      { name: 'Model', labels: months, values: pm },
      { name: 'Base rate', labels: months, values: pb },
    ], options: { chartColors: [HEX.TEAL, HEX.SOFT], lineSize: 2.5, lineDataSymbol: 'circle',
      lineDataSymbolSize: 6 } },
  ], chartBase({
    x: 0.6, y: 3.8, w: 7.75, h: 3.0, valAxisMinVal: 0, valAxisMaxVal: 1, valAxisMajorUnit: 0.25,
    valAxisLabelFormatCode: '0.00', catAxisLabelFontSize: 9, catAxisLabelRotate: -45, showLegend: true,
    legendPos: 't',
  }));

  card(s, 8.75, 1.8, 3.88, 4.95);
  label(s, 'WHY IT IS STILL A LEAD', 9.0, 2.05, 3.4, ORNG);
  txt(s, [
    { text: '83% of the gain comes from 3 of 19 months: May, June and August 2026.', options: { bullet: true, breakLine: true } },
    { text: 'The feature set is the best of 14 runs; its interval is not corrected for that choice.', options: { bullet: true, breakLine: true } },
    { text: 'Announcements are hand-coded, and recent ones are easier to find.', options: { bullet: true, breakLine: true } },
    { text: 'The fix is time: score the months after September 2026, which no one selected a model on.', options: { bullet: true, bold: true } },
  ], { x: 9.0, y: 2.45, w: 3.4, h: 3.0, fontSize: 13.5, color: INK, paraSpaceAfter: 9 });
  s.addShape(pres.ShapeType.roundRect, { x: 9.0, y: 5.45, w: 3.38, h: 1.1, fill: { color: WHITE }, rectRadius: 0.06,
    line: { type: 'none' } });
  txt(s, [
    { text: 'So far: ', options: { bold: true, color: TEAL } },
    { text: 'one month has been scored since the specification was chosen (Aug 2026). The model said 0.77, and an announcement followed.',
      options: { color: MUT } },
  ], { x: 9.15, y: 5.55, w: 3.1, h: 0.95, fontSize: 12 });

  notes(s, [
    '~60 seconds. Be the first to say what is wrong with the result',
    'Top: the real model scores 0.177; the best of 200 calendar-shifted copies scores 0.204 and the median 0.279. None does as well, so it is not just a trend',
    'Bottom: model probability (teal) against the base rate (grey). Shaded months had an announcement',
    'The gain is concentrated: May, June and August 2026 supply 83% of it, all in the 2026 run of announcements',
    'One clear miss: September 2025, where the model said 0.01 and an announcement came',
    'Selection: this set is the best of 14 runs (7 feature sets x 2 model families). The placebo is the part of the evidence that selection does not explain',
    'Collection effect: recent announcements are easier to find by hand, so the 2026 cluster may be partly ours',
    'The honest next test: score months after September 2026. Q3 results season (November) is the first chance',
    'Sources: results/national/8c_ice_control_placebo_draws.csv, 8d_mix_model_by_month.csv, outlook-card.md',
  ]);
}

/* ======================================================================
   9  STRETCH QUESTION: SITING
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Models' });
  head(s, '08 · STRETCH QUESTION', 'Siting follows car demand and track record');

  txt(s, 'State siting, tested Jul 2025 → Aug 2026 (11 announcements)', { x: 0.7, y: 1.8, w: 7.0, h: 0.3,
    fontSize: 12, bold: true, color: MUT });
  const labels = ['Base rate', 'Demand share, no fit', 'Announcement history', 'Share + history'];
  s.addChart(pres.ChartType.bar, [
    { name: 'AUC', labels, values: [0.50, 0.77, 0.75, 0.85] },
    { name: 'Top-5 hit rate', labels, values: [0.14, 0.45, 0.64, 0.64] },
  ], chartBase({
    x: 0.6, y: 2.15, w: 7.2, h: 4.5, barDir: 'bar', barGrouping: 'clustered', barGapWidthPct: 45,
    chartColors: [HEX.TEAL, HEX.VIOL], showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '0.00',
    valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 1, valGridLine: { style: 'none' },
    catAxisOrientation: 'maxMin', catAxisLabelFontSize: 12, showLegend: true, legendPos: 'b',
  }));

  [['0.85', 'AUC, share + history'], ['64%', 'announcing state was\nin our top five']].forEach((st, i) => {
    const x = 8.15 + i * 2.3;
    card(s, x, 1.8, 2.18, 1.6);
    txt(s, st[0], { x: x + 0.1, y: 1.95, w: 1.98, h: 0.68, fontSize: 34, bold: true, color: i ? VIOL : TEAL,
      align: 'center', fontFace: HEAD });
    txt(s, st[1], { x: x + 0.1, y: 2.7, w: 1.98, h: 0.6, fontSize: 12, color: MUT, align: 'center' });
  });

  const pts = [
    { c: TEAL, t: 'Cars, not all EVs', d: 'Once 4W share enters the model it takes over from total EV share (p = 0.007).' },
    { c: ORNG, t: 'Caveat: state size', d: 'Size alone scores AUC 0.77, the same as demand share. Read the rank, not the level.' },
    { c: VIOL, t: 'October 2026 top five', d: 'Maharashtra, Telangana, Tamil Nadu, Karnataka, Gujarat.' },
  ];
  let y = 3.68;
  pts.forEach((p) => {
    dot(s, 8.15, y + 0.05, p.c, 0.26);
    txt(s, p.t, { x: 8.55, y, w: 4.08, h: 0.34, fontSize: 15, bold: true, fontFace: HEAD });
    txt(s, p.d, { x: 8.55, y: y + 0.36, w: 4.08, h: 0.58, fontSize: 12.5, color: MUT });
    y += 1.0;
  });

  notes(s, [
    '~50 seconds. The stretch question answers yes, with one honest caveat',
    'Base rate picks the right state 14% of the time in its top five; ranking by demand share alone gets 45%, with no fitting',
    'A state’s own announcement history is as strong as demand; together they give AUC 0.85 and a 64% top-five hit rate',
    'Car share matters more than total EV share: once 4W share is in, total share drops out. Consistent with the market slide',
    'Caveat: a model on state size alone also scores 0.77, so we cannot say demand caused the siting. A high rank means a large EV market with a record of announcements',
    'The brief asked whether demand or incentives decide siting (the US IRA comparison). Our data cannot separate demand from size, and track record carries as much signal',
    'Sources: results/summary.md (state table), outlook-card.md',
  ]);
}

/* ======================================================================
   10  NEURAL NETWORKS
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Models' });
  head(s, '09 · NEURAL NETWORKS', 'Networks confirmed the findings, with one small win');

  const left = [
    { chip: 'AGREES', fill: TEAL, t: 'Announcement timing',
      d: 'An MLP picks the same segment-mix feature set by a different route: +34.1% Brier skill, ahead of all 200 placebos.' },
    { chip: 'TIES', fill: MUT, t: 'State siting',
      d: 'AUC 0.852 against the logit’s 0.85, but a worse top-five hit rate (0.55 vs 0.64). Seven training events leave little to learn.' },
  ];
  let y = 1.8;
  left.forEach((r) => {
    card(s, 0.7, y, 5.55, 2.3);
    chip(s, r.chip, 0.95, y + 0.25, 1.2, r.fill, WHITE);
    txt(s, r.t, { x: 0.95, y: y + 0.72, w: 5.0, h: 0.4, fontSize: 18, bold: true, fontFace: HEAD });
    txt(s, r.d, { x: 0.95, y: y + 1.18, w: 5.0, h: 0.95, fontSize: 13.5, color: MUT });
    y += 2.5;
  });

  card(s, 6.5, 1.8, 6.13, 4.8);
  chip(s, 'ONE SMALL WIN', 6.75, 2.05, 1.75, VIOL, WHITE);
  txt(s, 'Forecasting EV volume, 34 states × 92 months', { x: 6.75, y: 2.52, w: 5.7, h: 0.4, fontSize: 18,
    bold: true, fontFace: HEAD });
  txt(s, 'Sequence models mostly rediscover exponential smoothing. N-BEATS on the smoother’s residual beats it by 4.5%, one month ahead only.',
    { x: 6.75, y: 2.97, w: 5.65, h: 0.75, fontSize: 13.5, color: MUT });
  txt(s, 'Error reduction vs last month’s value, %  ·  46-month rolling backtest', { x: 6.75, y: 3.8,
    w: 5.65, h: 0.28, fontSize: 11, bold: true, color: MUT });
  s.addChart(pres.ChartType.bar, [{
    name: 'Skill vs naive', labels: ['Naive', 'Drift', 'Smoothing', 'N-BEATS', 'N-BEATS on smoothing'],
    values: [0.0, 0.4, 8.7, 10.9, 12.8],
  }], chartBase({
    x: 6.65, y: 4.08, w: 5.85, h: 2.4, barDir: 'col', chartColors: [HEX.VIOL], barGapWidthPct: 45,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '0.0', valAxisHidden: true,
    valAxisMinVal: 0, valAxisMaxVal: 15, valGridLine: { style: 'none' }, catAxisLabelFontSize: 10,
  }));

  notes(s, [
    '~55 seconds. The neural track asked whether a more flexible model finds what the simple ones missed',
    'National timing: an MLP (8 hidden units) lands on the same controls + production + mix set the logit chose: +34.1% Brier skill, beating all 200 placebos on every seed. Agreement, not a better number',
    'State siting: ties the logit on AUC, ranks worse. With 7 training events there is nothing for a network to add; prefer the logit',
    'Volume forecasting is the only target dense enough to train a network properly. GRU, LSTM, TCN, Transformer and N-BEATS all beat a random walk, but mostly by rediscovering exponential smoothing, which one fitted parameter does as well',
    'N-BEATS trained on the smoother’s residual beats smoothing by ~4.5% one month ahead, and held up in a 46-month rolling backtest. Beyond one month nothing beats smoothing reliably',
    'None of the networks is in the container: it serves the logit, on the feature set both families chose',
    'Sources: final-deliverable/model/nn-models-card.md, results/nn/summary.md',
  ]);
}

/* ======================================================================
   11  DELIVERABLE
   ====================================================================== */
pres.addSection({ title: 'Deliverable' });
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Deliverable' });
  head(s, '10 · DELIVERABLE', 'Shipped: a container that serves the outlook');

  const flow = [
    { t: 'Thurro data', d: 'production, registrations, filings' },
    { t: 'Build pipeline', d: 'clean data, then features' },
    { t: 'outlook.json', d: 'fitted models + input hashes' },
    { t: 'Docker image', d: 'HTTP service on a port' },
  ];
  flow.forEach((f, i) => {
    const x = 0.7 + i * 2.08;
    card(s, x, 1.8, 1.7, 1.05, i === 3 ? TEAL : TINT);
    txt(s, f.t, { x: x + 0.12, y: 1.92, w: 1.46, h: 0.32, fontSize: 13.5, bold: true, align: 'center',
      color: i === 3 ? WHITE : INK, fontFace: HEAD });
    txt(s, f.d, { x: x + 0.12, y: 2.27, w: 1.46, h: 0.5, fontSize: 10.5, align: 'center',
      color: i === 3 ? WHITE : MUT });
    if (i < 3) {
      s.addShape(pres.ShapeType.rightArrow, { x: x + 1.76, y: 2.2, w: 0.26, h: 0.26, fill: { color: HEX.SOFT },
        line: { type: 'none' } });
    }
  });

  card(s, 0.7, 3.1, 7.98, 2.15);
  label(s, 'WHAT IT SERVES', 0.95, 3.27, 7.4);
  const eps = [
    ['/outlook/national', 'P(an announcement next month), with each feature’s contribution'],
    ['/outlook/states?top=N', 'states ranked by P(named in next month’s announcement)'],
    ['/signals', 'per-company capex baseline, flagged is_baseline: no fitted model'],
    ['/ready  /metrics  /docs', 'self-check, Prometheus metrics, API documentation'],
  ];
  eps.forEach((e, i) => {
    const yy = 3.65 + i * 0.38;
    txt(s, e[0], { x: 0.95, y: yy, w: 2.75, h: 0.3, fontSize: 12.5, color: TEAL, fontFace: 'Courier New' });
    txt(s, e[1], { x: 3.75, y: yy, w: 4.8, h: 0.3, fontSize: 12.5, color: INK });
  });

  [['195', 'tests across the\nservice and models'], ['24/24', 'smoke checks on\nthe built image'], ['~6 s', 'from start to\nreporting healthy']]
    .forEach((st, i) => {
      const x = 0.7 + i * 2.72;
      card(s, x, 5.5, 2.54, 1.2);
      txt(s, st[0], { x: x + 0.18, y: 5.5, w: 1.2, h: 1.2, fontSize: 24, bold: true, color: TEAL, fontFace: HEAD,
        valign: 'middle' });
      txt(s, st[1], { x: x + 1.38, y: 5.5, w: 1.1, h: 1.2, fontSize: 11, color: MUT, valign: 'middle' });
    });

  card(s, 8.98, 1.8, 3.65, 4.9, DARK);
  txt(s, 'WHAT IT SAYS NOW', { x: 9.25, y: 2.02, w: 3.2, h: 0.28, fontSize: 11, bold: true, color: LTEAL, charSpacing: 1.4 });
  txt(s, '0.85', { x: 9.25, y: 2.35, w: 3.2, h: 0.85, fontSize: 48, bold: true, color: WHITE, fontFace: HEAD });
  txt(s, 'P(announcement in October 2026), against a base rate of 0.34', { x: 9.25, y: 3.22, w: 3.15, h: 0.55,
    fontSize: 12.5, color: HEX.ONDARK });
  txt(s, [
    { text: 'Biggest drivers', options: { bold: true, color: WHITE, breakLine: true } },
    { text: 'export share +2.05 log-odds; a record EV production month +1.22', options: { color: HEX.ONDARK } },
  ], { x: 9.25, y: 3.9, w: 3.15, h: 0.85, fontSize: 12.5 });
  txt(s, [
    { text: 'Top five states', options: { bold: true, color: WHITE, breakLine: true } },
    { text: 'Maharashtra, Telangana, Tamil Nadu, Karnataka, Gujarat', options: { color: HEX.ONDARK } },
  ], { x: 9.25, y: 4.85, w: 3.15, h: 0.85, fontSize: 12.5 });
  txt(s, 'October has closed: the data lags the calendar, and every response says so.', { x: 9.25, y: 5.85,
    w: 3.15, h: 0.65, fontSize: 11, italic: true, color: HEX.ONDARK });

  notes(s, [
    '~55 seconds. What a consumer of this work actually gets',
    'One Docker image: the fitted models, the feature snapshot they read, and an HTTP server. Any Docker host can run it; healthy in about 6 seconds',
    'The models are fitted offline into outlook.json, along with a sha256 of every input file, so a given image tag always serves the same numbers',
    '/outlook/national gives the probability of an announcement next month and each feature’s contribution in log-odds, so every number explains itself',
    '/outlook/states ranks the states. /signals serves the per-company capex null baseline, flagged so a consumer can refuse to act on it',
    'At load the service recomputes every stored probability; a difference above 1e-9 keeps it from reporting ready',
    'Today’s outlook: 0.85 for October 2026 against a base rate of 0.34, driven by a high export share and a record EV production month',
    'Operations: Prometheus metrics, one JSON log line per request, OpenTelemetry tracing, picks up a rebuilt panel without a restart',
    'Sources: final-deliverable/README.md, model/outlook-card.md, PR #16',
  ]);
}

/* ======================================================================
   12  CLOSE: SCORECARD AND NEXT STEPS
   ====================================================================== */
pres.addSection({ title: 'Close' });
{
  const s = pres.addSlide({ masterName: 'CLOSE_DARK', sectionTitle: 'Close' });
  head(s, '11 · AGAINST WHAT WE SAID IN SEPTEMBER', 'A defensible answer, and what would settle it');

  const STATUS = {
    MET: { fill: LTEAL, color: INK },
    CHANGED: { fill: HEX.LILAC, color: INK },
    MISSED: { fill: HEX.PEACH, color: INK },
  };
  const rows = [
    ['A defensible answer, not a positive one', 'MET', 'Volume: null on both dependent variables. Mix: a lead, reported with its limits.'],
    ['Beat a baseline', 'MET', '+34% Brier skill over the base rate, with an ICE-production control.'],
    ['Placebo: the lead must vanish', 'MET', '0 of 200 shifted copies did as well.'],
    ['45–75 dated events for power', 'MISSED', '34 events, 12 event months. Capex added 182 rows, but annual.'],
    ['Fix the lag in advance (k = 3)', 'CHANGED', 'Out-of-sample tests instead; selection over 14 runs disclosed.'],
    ['Stretch: where it is sited', 'MET', 'AUC 0.85; top-five hit rate 64%.'],
  ];
  txt(s, 'WHAT WE COMMITTED TO', { x: 0.7, y: 1.8, w: 3.0, h: 0.28, fontSize: 11, bold: true, color: LTEAL, charSpacing: 1.4 });
  let y = 2.2;
  rows.forEach((r) => {
    txt(s, r[0], { x: 0.7, y, w: 3.0, h: 0.6, fontSize: 13.5, bold: true, color: WHITE });
    chip(s, r[1], 3.8, y + 0.02, 1.08, STATUS[r[1]].fill, STATUS[r[1]].color);
    txt(s, r[2], { x: 5.05, y, w: 3.35, h: 0.62, fontSize: 12, color: HEX.ONDARK });
    y += 0.7;
  });

  card(s, 8.75, 1.8, 3.88, 4.25, DARK2);
  txt(s, 'WHAT WOULD SETTLE IT', { x: 9.0, y: 2.0, w: 3.4, h: 0.28, fontSize: 11, bold: true, color: LTEAL, charSpacing: 1.4 });
  const next = [
    ['Score the unseen months', 'Every month after Sept 2026, once its announcements are coded.'],
    ['Read FY27 capex filings', 'Mid-2027: do the FY26–27 announcements turn into spending?'],
    ['Separate demand from size', 'More siting events, so the two can be told apart.'],
  ];
  y = 2.45;
  next.forEach((n, i) => {
    numberBadge(s, i + 1, 9.0, y, TEAL, 0.42);
    txt(s, n[0], { x: 9.6, y: y - 0.02, w: 2.85, h: 0.32, fontSize: 14, bold: true, color: WHITE, fontFace: HEAD });
    txt(s, n[1], { x: 9.6, y: y + 0.33, w: 2.85, h: 0.75, fontSize: 12, color: HEX.ONDARK });
    y += 1.17;
  });

  txt(s, 'The hard part of alternative data was the dependent variable, not the model.', { x: 0.7, y: 6.35,
    w: 8.0, h: 0.4, fontSize: 16, bold: true, italic: true, color: WHITE, fontFace: HEAD });
  txt(s, 'Thank you  ·  Questions', { x: 8.75, y: 6.35, w: 3.88, h: 0.4, fontSize: 16, bold: true, color: LTEAL,
    align: 'right', fontFace: HEAD });
  txt(s, 'Slide design and layout generated with Claude (Anthropic Claude Code)', { x: 8.75, y: 6.78, w: 3.88,
    h: 0.2, fontSize: 9, color: HEX.ONDARK, align: 'right' });

  notes(s, [
    '~60 seconds. Close the loop on the criteria we set in September; do not read every row',
    'We said success was a defensible answer, not a positive one. We have one: headline volume does not lead investment, and the mix signal is reported with its limits',
    'Baseline and placebo: both met, and we strengthened the baseline (ICE control instead of a time trend)',
    'Missed: the power target. We needed 45–75 dated events and have 34. The capex rebuild added 182 company-years, but capex is annual, which buys precision, not time',
    'Changed: we planned to fix the lag at k = 3 in advance. We used walk-forward tests and a placebo instead, and disclose that the winning feature set is the best of 14',
    'What would settle it: (1) score months after Sept 2026, which no model was selected on; (2) read FY27 capex filings in mid-2027 to see whether the FY26–27 announcements become spending; (3) more siting events to separate demand from state size',
    'Closing line: the investment-tracking feed had no EV content, so most of the work was building a dependent variable we could trust',
  ]);
}

/* ======================================================================
   BACKUP 1  DATA PROBLEMS
   ====================================================================== */
pres.addSection({ title: 'Backup' });
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Backup' });
  head(s, 'BACKUP · DATA LESSONS', 'Data problems we found and fixed along the way');

  const probs = [
    ['The investment feed had no EV content', 'Two automotive rows, 113 of 115 energy-storage rows are oil and gas, and every row shares one snapshot date.'],
    ['The connector can drop rows silently', 'Its row cap scales with row width, and small results come back inline instead of on disk. Both are documented in data/raw/QUERIES.md.'],
    ['A partial month looked like a collapse', 'August 2026 production had 5 of 11 OEMs and read as an 88% drop. Refreshed on 22 October.'],
    ['Capex sits under two metric names', 'They add rather than alternate: coalescing them would zero out Hero’s entire capex history.'],
    ['Feeds spell companies differently', '“TVS MOTOR COMPANY” vs “TVS MOTOR”: one shared name map silently drops TVS.'],
    ['The state panel is sparse', 'Zero-registration months have no row; 21 of 36 states have gaps, so shifting one row is not always a one-month lag.'],
  ];
  probs.forEach((p, i) => {
    const x = 0.7 + (i % 3) * 4.03, y = 1.85 + Math.floor(i / 3) * 2.45;
    card(s, x, y, 3.84, 2.25);
    dot(s, x + 0.25, y + 0.27, i === 0 ? ORNG : TEAL, 0.26);
    txt(s, p[0], { x: x + 0.65, y: y + 0.22, w: 3.0, h: 0.62, fontSize: 15, bold: true, fontFace: HEAD });
    txt(s, p[1], { x: x + 0.25, y: y + 0.95, w: 3.35, h: 1.2, fontSize: 14, color: MUT });
  });

  notes(s, [
    'Pull up only if asked about data quality',
    'Each of these silently corrupts a series if missed; each is now handled in code and documented',
    'Investment feed: unusable as a dependent variable regardless of content, since it has one snapshot date',
    'Connector: the row cap shrinks as rows get wider, so a wider query returns fewer rows without an error',
    'August 2026: only 5 of 11 OEMs had reported at first pull; the 22 October refresh filled it',
    'Capex: two additive metric names. Ola, Bajaj and Syrma report both in one year; Hero reports only the second',
    'State panel: the neural-network track reindexes onto a complete month grid before lagging',
    'Sources: data/README.md, data/raw/QUERIES.md, PR #6',
  ]);
}

/* ======================================================================
   BACKUP 2  FULL MODEL TABLES
   ====================================================================== */
{
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Backup' });
  head(s, 'BACKUP · FULL RESULTS', 'Every model, on the same splits');

  const H = (t) => ({ text: t, options: { bold: true, color: HEX.MUT, fontSize: 11 } });
  const R = (cells, hi) => cells.map((t) => ({ text: t, options: hi ? { bold: true, color: HEX.TEAL } : {} }));
  const tbl = { fontSize: 11.5, color: HEX.INK, border: { type: 'solid', pt: 0.75, color: HEX.LINE },
    valign: 'middle', margin: [0.03, 0.08, 0.03, 0.08] };

  label(s, 'NATIONAL  ·  WALK-FORWARD, NEXT MONTH', 0.7, 1.8, 7.2);
  s.addTable([
    [H('Model'), H('Brier'), H('AUC'), H('Skill'), H('90% CI of gain')],
    R(['Base rate', '0.256', '0.64', '—', '—']),
    R(['Logit, controls only', '0.255', '0.66', '+0.5%', '[−0.041, 0.041]']),
    R(['Poisson, core', '0.238', '0.71', '+6.8%', '[−0.010, 0.043]']),
    R(['Logit L2, core', '0.236', '0.69', '+7.8%', '[−0.042, 0.078]']),
    R(['Lasso, all features', '0.229', '0.64', '+10.6%', '[−0.020, 0.075]']),
    R(['Random forest, all', '0.236', '0.71', '+7.9%', '[−0.021, 0.057]']),
    R(['Gradient boosting, all', '0.272', '0.73', '−6.5%', '[−0.115, 0.077]']),
    R(['MLP (8), production + mix', '0.168', '0.78', '+34.1%', '[0.005, 0.172]']),
    R(['Logit L2, production + mix, ICE control†', '0.177', '0.84', '+33.6%', '[0.020, 0.164]'], true),
  ], Object.assign({ x: 0.7, y: 2.15, w: 7.2, colW: [3.2, 0.85, 0.75, 0.9, 1.5], rowH: 0.36 }, tbl));
  txt(s, 'Rows 1–8: 18 test months, 7 events. † Served model, after the October data refresh: 19 test months, 8 events.',
    { x: 0.7, y: 5.95, w: 7.2, h: 0.5, fontSize: 10.5, italic: true, color: MUT });

  label(s, 'STATE  ·  TEST AFTER JUN 2025', 8.3, 1.8, 4.3);
  s.addTable([
    [H('Model'), H('AUC'), H('Avg prec.'), H('Top 5')],
    R(['Base rate', '0.50', '0.023', '0.14']),
    R(['Demand-share rank', '0.77', '0.064', '0.45']),
    R(['Logit, size', '0.77', '0.071', '0.45']),
    R(['Logit, share', '0.77', '0.064', '0.45']),
    R(['Logit, history', '0.75', '0.087', '0.64']),
    R(['Random forest, all', '0.85', '0.102', '0.45']),
    R(['MLP (8), all', '0.85', '0.120', '0.55']),
    R(['Logit, share + history†', '0.85', '0.124', '0.64'], true),
  ], Object.assign({ x: 8.3, y: 2.15, w: 4.33, colW: [2.0, 0.65, 0.93, 0.75], rowH: 0.36 }, tbl));
  txt(s, '† Served model. 11 test events.', { x: 8.3, y: 5.6, w: 4.33, h: 0.3, fontSize: 10.5, italic: true, color: MUT });

  notes(s, [
    'Reference only. Every model ran on the same splits and metrics',
    'Before the mix features, the best national model was the lasso at +10.6%, and no interval cleared zero',
    'The served national model is the bottom row; the MLP row is the independent agreement',
    'State: the served model ties the random forest and the MLP on AUC and beats both on top-five hit rate',
    'Sources: final-deliverable/model/results/summary.md, results/nn/summary.md, outlook-card.md',
  ]);
}

/* ---------- write, then give the deck its theme ---------- */
async function applyTheme(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const part = 'ppt/theme/theme1.xml';
  const slots = ['dk1', 'lt1', 'dk2', 'lt2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6', 'hlink', 'folHlink'];
  const scheme = `<a:clrScheme name="${THEME.name}">` +
    slots.map((k) => `<a:${k}><a:srgbClr val="${THEME.colors[k]}"/></a:${k}>`).join('') + '</a:clrScheme>';
  const theme = (await zip.file(part).async('string'))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, h) => `${h}${THEME.name}"`);
  if (!theme.includes(scheme)) throw new Error('theme1.xml has no colour scheme to replace');
  zip.file(part, theme);
  for (const name of Object.keys(zip.files)) {
    if (zip.files[name].dir) { delete zip.files[name]; continue; }
    if (!name.endsWith('.xml')) continue;
    const xml = await zip.file(name).async('string');
    const bad = xml.match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name}: a scheme colour reached a hex-only option (${bad[1]})`);
    // pptxgenjs writes <c:crossesAt val="autoZero"/>, which PowerPoint offers to repair.
    if (xml.includes('<c:crossesAt val="autoZero"/>')) {
      zip.file(name, xml.replaceAll('<c:crossesAt val="autoZero"/>', '<c:crosses val="autoZero"/>'));
    }
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
}

pres.writeFile({ fileName: OUT })
  .then(() => applyTheme(OUT))
  .then(() => console.log('written:', OUT))
  .catch((e) => { console.error(e); process.exit(1); });
