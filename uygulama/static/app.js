import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';

/* ================================================================
   Şema: her dişli tipi için form alanları
   ================================================================ */

const STD_M = [0.5, 0.6, 0.8, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

const profile = (o = {}) => ({
  title: 'Diş profili', fields: [
    { k: 'm', l: 'Modül m', u: 'mm', d: o.m ?? 2, min: 0.05, max: 50, step: 0.05, list: STD_M },
    { k: 'pa', l: 'Kavrama açısı α', u: '°', d: o.pa ?? 20, min: 10, max: 35, step: 0.5 },
    { k: 'width', l: o.wl ?? 'Diş genişliği b', u: 'mm', d: o.width ?? 10, min: 0.5, step: 1 },
    ...(o.noBacklash ? [] : [{ k: 'backlash', l: 'Boşluk (backlash)', u: 'mm', d: 0.1, min: 0, max: 5, step: 0.05 }]),
    { k: 'root_fillet', l: 'Dip radyüsü', s: '× modül', d: 0, min: 0, max: 0.5, step: 0.05 },
    { k: 'tip_fillet', l: 'Uç radyüsü', s: '× modül', d: 0, min: 0, max: 0.5, step: 0.05 },
    ...(o.undercut ? [{ k: 'undercut', l: 'Alttan kesilme (undercut) hesabı', t: 'bool', d: true }] : []),
  ]
});

const bore = (p, title, open = false) => ({
  title, collapsed: !open, fields: [
    { k: p + 'bore_d', l: 'Delik çapı', s: '0 = delik yok', u: 'mm', d: 0, min: 0, step: 1 },
    { k: p + 'bore_type', l: 'Delik tipi', t: 'sel', d: 'daire', opts: [
      ['daire', 'Dairesel'], ['kama', 'Kamalı (DIN 6885)'], ['dflat', 'D-kesit'],
      ['altigen', 'Altıgen'], ['yok', 'Yok']] },
    { k: p + 'hub_d', l: 'Göbek çapı', s: '0 = göbek yok', u: 'mm', d: 0, min: 0, step: 1 },
    { k: p + 'hub_len', l: 'Göbek boyu', u: 'mm', d: 0, min: 0, step: 1 },
  ]
});

const TYPES = [
  { id: 'duz', label: 'Düz', icon: 'spur', sections: [
    { title: 'Dişliler', fields: [
      { k: 'z1', l: 'Diş sayısı z₁ (A)', d: 14, min: 3, max: 400, step: 1, int: true },
      { k: 'pair', l: 'Karşı dişli (B) oluştur', t: 'bool', d: true },
      { k: 'z2', l: 'Diş sayısı z₂ (B)', d: 29, min: 3, max: 400, step: 1, int: true, show: v => v.pair },
      { k: 'x1', l: 'Profil kaydırma x₁', d: 0, min: -1, max: 1.5, step: 0.05 },
      { k: 'x2', l: 'Profil kaydırma x₂', d: 0, min: -1, max: 1.5, step: 0.05, show: v => v.pair },
    ] },
    profile({ undercut: true }),
    bore('a_', 'Dişli A — delik / göbek', true), bore('b_', 'Dişli B — delik / göbek'),
  ] },
  { id: 'helisel', label: 'Helisel', icon: 'helical', sections: [
    { title: 'Dişliler', fields: [
      { k: 'z1', l: 'Diş sayısı z₁ (A)', d: 14, min: 3, max: 400, step: 1, int: true },
      { k: 'pair', l: 'Karşı dişli (B) oluştur', t: 'bool', d: true },
      { k: 'z2', l: 'Diş sayısı z₂ (B)', d: 29, min: 3, max: 400, step: 1, int: true, show: v => v.pair },
      { k: 'beta', l: 'Helis açısı β', u: '°', d: 20, min: -60, max: 60, step: 1 },
      { k: 'm_kind', l: 'Girilen modül', s: 'alın: d₀ = z·m', t: 'sel', d: 'normal', opts: [
        ['normal', 'Normal modül mₙ'], ['alin', 'Alın modülü mₜ']] },
      { k: 'herringbone', l: 'Çift helis (balıksırtı)', t: 'bool', d: false },
      { k: 'x1', l: 'Profil kaydırma x₁', d: 0, min: -1, max: 1.5, step: 0.05 },
      { k: 'x2', l: 'Profil kaydırma x₂', d: 0, min: -1, max: 1.5, step: 0.05, show: v => v.pair },
    ] },
    profile({ undercut: true, width: 12 }),
    bore('a_', 'Dişli A — delik / göbek', true), bore('b_', 'Dişli B — delik / göbek'),
  ] },
  { id: 'ic', label: 'İç dişli', icon: 'ring', sections: [
    { title: 'Dişliler', fields: [
      { k: 'z_ring', l: 'Halka diş sayısı', d: 48, min: 12, max: 400, step: 1, int: true },
      { k: 'z1', l: 'Pinyon diş sayısı', d: 17, min: 3, max: 400, step: 1, int: true },
      { k: 'x1', l: 'Pinyon profil kaydırma', d: 0, min: -1, max: 1.5, step: 0.05 },
      { k: 'rim', l: 'Dış çember kalınlığı', s: '× modül', d: 2.5, min: 1.2, max: 20, step: 0.1 },
    ] },
    profile(), bore('a_', 'Pinyon — delik / göbek', true),
  ] },
  { id: 'konik', label: 'Konik', icon: 'bevel', sections: [
    { title: 'Dişliler', fields: [
      { k: 'z1', l: 'Pinyon z₁', d: 14, min: 5, max: 200, step: 1, int: true },
      { k: 'z2', l: 'Çark z₂', d: 29, min: 5, max: 200, step: 1, int: true },
      { k: 'shaft_angle', l: 'Eksenler arası açı Σ', u: '°', d: 90, min: 20, max: 160, step: 1 },
      { k: 'spiral', l: 'Spiral açısı', s: 'yaklaşık', u: '°', d: 0, min: -45, max: 45, step: 1 },
      { k: 'x1', l: 'Profil kaydırma (±)', d: 0, min: -0.8, max: 0.8, step: 0.05 },
    ] },
    profile({ width: 8, wl: 'Diş boyu b', noBacklash: true }),
    bore('a_', 'Pinyon — delik / göbek', true), bore('b_', 'Çark — delik / göbek'),
  ] },
  { id: 'kremayer', label: 'Kremayer', icon: 'rack', sections: [
    { title: 'Pinyon + kremayer', fields: [
      { k: 'z1', l: 'Pinyon diş sayısı', d: 16, min: 5, max: 300, step: 1, int: true },
      { k: 'z_rack', l: 'Kremayer diş sayısı', d: 20, min: 3, max: 400, step: 1, int: true },
      { k: 'beta', l: 'Helis açısı β', s: '0 = düz', u: '°', d: 0, min: -45, max: 45, step: 1 },
    ] },
    profile(), bore('a_', 'Pinyon — delik / göbek', true),
  ] },
  { id: 'sikloid', label: 'Sikloid', icon: 'cycloid', sections: [
    { title: 'Dişliler', fields: [
      { k: 'z1', l: 'Diş sayısı z₁', d: 12, min: 4, max: 300, step: 1, int: true },
      { k: 'z2', l: 'Diş sayısı z₂', d: 24, min: 4, max: 300, step: 1, int: true },
      { k: 'cyc', l: 'Yuvarlanma çemberi', s: '× taksimat yarıçapı', d: 0.5, min: 0.1, max: 1, step: 0.05 },
      { k: 'm', l: 'Modül m', u: 'mm', d: 2, min: 0.05, max: 50, step: 0.05, list: STD_M },
      { k: 'width', l: 'Genişlik b', u: 'mm', d: 10, min: 0.5, step: 1 },
      { k: 'backlash', l: 'Boşluk', u: 'mm', d: 0.1, min: 0, max: 5, step: 0.05 },
    ] },
    bore('a_', 'Dişli A — delik / göbek', true), bore('b_', 'Dişli B — delik / göbek'),
  ] },
  { id: 'planet', label: 'Planet', icon: 'planet', sections: [
    { title: 'Planet dişli seti', fields: [
      { k: 'z_sun', l: 'Güneş diş sayısı', d: 15, min: 5, max: 200, step: 1, int: true },
      { k: 'z_ring', l: 'Halka diş sayısı', s: 'fark çift olmalı', d: 51, min: 20, max: 400, step: 1, int: true },
      { k: 'n_planet', l: 'Gezegen sayısı', d: 3, min: 1, max: 12, step: 1, int: true },
      { k: 'beta', l: 'Helis açısı β', s: '0 = düz', u: '°', d: 0, min: -45, max: 45, step: 1 },
    ] },
    profile(), bore('a_', 'Güneş — delik / göbek', true), bore('b_', 'Gezegen — delik'),
  ] },
  { id: 'sonsuz', label: 'Sonsuz vida', icon: 'worm', sections: [
    { title: 'Sonsuz vida', fields: [
      { k: 'z1', l: 'Ağız sayısı z₁', d: 2, min: 1, max: 6, step: 1, int: true },
      { k: 'z2', l: 'Çark diş sayısı z₂', d: 30, min: 10, max: 150, step: 1, int: true },
      { k: 'm', l: 'Eksenel modül mₓ', u: 'mm', d: 2, min: 0.2, max: 20, step: 0.05, list: STD_M },
      { k: 'q', l: 'Çap katsayısı q', d: 10, min: 5, max: 20, step: 0.5 },
      { k: 'width', l: 'Çark genişliği', u: 'mm', d: 12, min: 1, step: 1 },
      { k: 'worm_len', l: 'Vida boyu', s: '0 = otomatik', u: 'mm', d: 0, min: 0, step: 1 },
    ] },
    bore('a_', 'Vida — delik'), bore('b_', 'Çark — delik / göbek', true),
  ] },
  { id: 'mil', label: 'Kamalı mil', icon: 'spline', sections: [
    { title: 'Evolvent kamalı mil', fields: [
      { k: 'm', l: 'Modül m', u: 'mm', d: 1, min: 0.25, max: 10, step: 0.05 },
      { k: 'z1', l: 'Diş sayısı z', d: 16, min: 6, max: 60, step: 1, int: true },
      { k: 'pa', l: 'Kavrama açısı', u: '°', d: 30, min: 20, max: 45, step: 7.5 },
      { k: 'd_tip', l: 'Diş üstü çapı', s: '0 = m(z+1)−0,2', u: 'mm', d: 0, min: 0, step: 0.05 },
      { k: 'd_root', l: 'Diş dibi çapı', s: '0 = m(z−1,5)+0,1', u: 'mm', d: 0, min: 0, step: 0.05 },
      { k: 'offset', l: 'Yanak düzeltmesi', s: '− = incelir (baskı telafisi)', u: 'mm', d: 0, min: -1, max: 1, step: 0.01 },
      { k: 'width', l: 'Mil boyu', u: 'mm', d: 30, min: 1, step: 1 },
    ] },
    { title: 'Eş göbek', fields: [
      { k: 'with_hub', l: 'Eşleşen göbek oluştur', t: 'bool', d: true },
      { k: 'hub_clear', l: 'Yanak boşluğu', u: 'mm', d: 0.15, min: 0, max: 1, step: 0.05, show: v => v.with_hub },
      { k: 'hub_d', l: 'Göbek dış çapı', s: '0 = otomatik', u: 'mm', d: 0, min: 0, step: 1, show: v => v.with_hub },
    ] },
  ] },
  { id: 'diferansiyel', label: 'Diferansiyel', icon: 'diff', sections: [
    { title: 'Diferansiyel kutusu', fields: [
      { k: 'z_side', l: 'Aks dişlisi z', d: 16, min: 8, max: 60, step: 1, int: true },
      { k: 'z_pin', l: 'Uydu dişlisi z', d: 10, min: 6, max: 40, step: 1, int: true },
      { k: 'n_pin', l: 'Uydu sayısı', s: '2 veya 4', d: 2, min: 2, max: 4, step: 2, int: true },
      { k: 'm', l: 'Modül m', u: 'mm', d: 2, min: 0.3, max: 20, step: 0.05, list: STD_M },
      { k: 'width', l: 'Diş boyu b', u: 'mm', d: 8, min: 1, step: 1 },
      { k: 'pa', l: 'Kavrama açısı α', u: '°', d: 20, min: 14.5, max: 30, step: 0.5 },
    ] },
    { title: 'Ayna + tahrik pinyonu', fields: [
      { k: 'z_ring', l: 'Ayna dişlisi z', d: 41, min: 20, max: 120, step: 1, int: true },
      { k: 'z_drive', l: 'Tahrik pinyonu z', d: 11, min: 6, max: 40, step: 1, int: true },
      { k: 'm_ring', l: 'Ayna modülü', u: 'mm', d: 2.5, min: 0.3, max: 20, step: 0.05, list: STD_M },
      { k: 'width_ring', l: 'Ayna diş boyu', u: 'mm', d: 12, min: 1, step: 1 },
    ] },
    { title: 'Simülasyon', fields: [
      { k: 'turn', l: 'Viraj (hız farkı)', s: '0 = düz yol, + = sağa dönüş', u: '%', d: 30, min: -100, max: 100, step: 5 },
    ] },
  ] },
  { id: 'reduktor', label: 'Redüktör', icon: 'reducer', custom: true },
];

const LABELS = {
  z: 'Diş sayısı z', m: 'Modül m', m_t: 'Alın modülü mₜ', d0: 'Taksimat Ø d₀', da: 'Diş üstü Ø dₐ', df: 'Diş dibi Ø d_f',
  db: 'Temel Ø d_b', x: 'Profil kaydırma x', b: 'Genişlik b', a: 'Eksen mesafesi a', i: 'Çevrim oranı i',
  eps_a: 'Kavrama oranı εα', k: 'Baş kısaltma k', 'β': 'Helis açısı β', 'δ': 'Koni açısı δ', 'δ1': 'Pinyon koni δ₁',
  'δ2': 'Çark koni δ₂', 'Σ': 'Eksen açısı Σ', R: 'Koni mesafesi R', L: 'Boy L', 'γ': 'Helis (adım) açısı γ',
  v_per_rad: 'Kremayer yolu / rad', z_gezegen: 'Gezegen diş sayısı', n_gezegen: 'Gezegen adedi',
  'i_güneş_taşıyıcı': 'Oran güneş→taşıyıcı', 'η_tahmini': 'Verim η (tahmini)',
  'kendiliğinden_kilit': 'Kendiliğinden kilit', D_temel: 'Temel Ø', i_hedef: 'Hedef oran',
  'i_gerçek': 'Gerçek oran', 'η_toplam': 'Toplam verim η', 'n_çıkış': 'Çıkış devri (d/dk)',
  d: 'Çap d', n_rpm: 'Devir (d/dk)', tip: 'Tip', malzeme: 'Malzeme', 'D_dış': 'Dış Ø',
  'α': 'Kavrama açısı', 'D_uç': 'Diş üstü Ø', D_taksimat: 'Taksimat Ø', D_dip: 'Diş dibi Ø',
  ofset: 'Yanak düzeltmesi', 'boşluk': 'Yanak boşluğu', i_ayna: 'Ayna oranı i',
  sol_tekerlek: 'Sol tekerlek hızı', 'sağ_tekerlek': 'Sağ tekerlek hızı', 'δ_aks': 'Aks dişlisi koni δ',
  'δ_uydu': 'Uydu koni δ',
};
const UNITS = { 'δ_aks': '°', 'δ_uydu': '°', m_t: 'mm', d0: 'mm', da: 'mm', df: 'mm', db: 'mm', b: 'mm', a: 'mm', m: 'mm', R: 'mm', L: 'mm', d: 'mm',
  'β': '°', 'δ': '°', 'δ1': '°', 'δ2': '°', 'Σ': '°', 'γ': '°', 'α': '°', v_per_rad: 'mm', 'D_dış': 'mm',
  D_temel: 'mm', 'D_uç': 'mm', D_taksimat: 'mm', D_dip: 'mm', ofset: 'mm', 'boşluk': 'mm' };

/* ================================================================
   Simgeler
   ================================================================ */

function gearPts(cx, cy, r, n, h, inner = false) {
  const pts = []; const s = Math.PI / n;
  const ro = inner ? r - h : r, ri = inner ? r : r - h;
  for (let i = 0; i < n; i++) {
    const a = i * 2 * s;
    [[ri, a - s * 0.55], [ro, a - s * 0.3], [ro, a + s * 0.3], [ri, a + s * 0.55]]
      .forEach(([rr, t]) => pts.push(`${(cx + rr * Math.cos(t)).toFixed(2)},${(cy + rr * Math.sin(t)).toFixed(2)}`));
  }
  return pts.join(' ');
}
const G = (cx, cy, r, n, h = 1.8) => `<polygon points="${gearPts(cx, cy, r, n, h)}"/>`;
const ICONS = {
  spur: `${G(10, 16, 7.5, 10)}${G(20.5, 9, 5.2, 7)}<circle cx="10" cy="16" r="1.8"/><circle cx="20.5" cy="9" r="1.4"/>`,
  helical: `${G(14, 14, 10, 12)}<path d="M9 7 L12 21 M13 7 L16 21 M17 7 L20 21"/>`,
  ring: `<circle cx="14" cy="14" r="12"/><polygon points="${gearPts(14, 14, 10, 14, 1.8, true)}"/>${G(17.5, 14, 4.8, 7, 1.5)}`,
  bevel: `<path d="M4 20 L9 8 L15 8 L20 20 Z"/><path d="M15 12 L25 9 L25 21 L15 18"/>`,
  rack: `${G(14, 10, 7, 9)}<path d="M2 25 V20 H4 L5 18 H7 L8 20 H10 L11 18 H13 L14 20 H16 L17 18 H19 L20 20 H22 L23 18 H25 L26 20 V25 Z"/>`,
  cycloid: `<path d="${(() => { let d = ''; for (let i = 0; i < 9; i++) { const a = i * 2 * Math.PI / 9, b = a + Math.PI / 9; d += `${i ? 'L' : 'M'}${(14 + 11 * Math.cos(a)).toFixed(1)} ${(14 + 11 * Math.sin(a)).toFixed(1)} Q${(14 + 13 * Math.cos(a + 0.35)).toFixed(1)} ${(14 + 13 * Math.sin(a + 0.35)).toFixed(1)} ${(14 + 8 * Math.cos(b)).toFixed(1)} ${(14 + 8 * Math.sin(b)).toFixed(1)} `; } return d + 'Z'; })()}"/><circle cx="14" cy="14" r="2"/>`,
  planet: `<circle cx="14" cy="14" r="12.5"/><circle cx="14" cy="14" r="3.5"/><circle cx="14" cy="6.5" r="3.5"/><circle cx="7.5" cy="18" r="3.5"/><circle cx="20.5" cy="18" r="3.5"/>`,
  worm: `<rect x="3" y="17" width="22" height="7" rx="2"/><path d="M7 17 L9 24 M11 17 L13 24 M15 17 L17 24 M19 17 L21 24"/>${G(14, 8, 6, 10, 1.5)}`,
  spline: `${G(14, 14, 10, 12, 2.4)}<circle cx="14" cy="14" r="4"/>`,
  diff: `<path d="M4 9 L9 4 L9 24 L4 19 Z"/><path d="M24 9 L19 4 L19 24 L24 19 Z"/><circle cx="14" cy="8" r="3"/><circle cx="14" cy="20" r="3"/><path d="M14 11 V17"/>`,
  reducer: `<rect x="2.5" y="4" width="23" height="20" rx="2.5"/>${G(10, 16, 5, 8, 1.4)}${G(18, 11, 4, 7, 1.3)}`,
};
const iconSvg = n => `<svg viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round">${ICONS[n]}</svg>`;

/* ================================================================
   Durum
   ================================================================ */

const $ = s => document.querySelector(s);
const LS_KEY = 'cark-olusturucu.v1';
let store = {};
try { store = JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; } catch { store = {}; }
const save = () => { try { localStorage.setItem(LS_KEY, JSON.stringify(store)); } catch { /* yok say */ } };

const state = {
  kind: store.kind || 'duz',
  vals: store.vals || {},
  meta: { materials: ['PLA', 'PETG', 'ABS'], k0: {} },
  current: null,
  seq: 0,
};

function defaults(t) {
  const v = {};
  (t.sections || []).forEach(sec => sec.fields.forEach(f => { v[f.k] = f.d; }));
  return v;
}

function redDefaults() {
  return {
    P_in: 0.25, n_in: 1500, i_total: 9, lubricated: false, backlash: 0.15, Lh: 10000, S: 1.5,
    bed: 220, bore_type: 'kama', objective: 'koaksiyel',
    stages: [
      { gtype: 'helisel', material: 'PETG', i_stage: 3, beta: 15, K0: 1.25, z1: 2, q: 10, z1_gear: '' },
      { gtype: 'duz', material: 'PETG', i_stage: 3, beta: 15, K0: 1.25, z1: 2, q: 10, z1_gear: '' },
    ],
  };
}

function vals(kind = state.kind) {
  const t = TYPES.find(x => x.id === kind);
  if (!state.vals[kind]) state.vals[kind] = t.custom ? redDefaults() : defaults(t);
  const cur = state.vals[kind];
  // Eksik alanları YERİNDE tamamla: form dinleyicileri bu nesneye yazıyor,
  // yeni nesne oluşturmak kullanıcı değişikliklerini koparırdı.
  if (!t.custom) {
    for (const [k, d] of Object.entries(defaults(t))) if (!(k in cur)) cur[k] = d;
  }
  return cur;
}

/* ================================================================
   Form oluşturma
   ================================================================ */

function renderTypes() {
  $('#types').innerHTML = TYPES.map(t =>
    `<button class="type-btn${t.id === state.kind ? ' on' : ''}" data-id="${t.id}" title="${t.label}">${iconSvg(t.icon)}<span>${t.label}</span></button>`).join('');
  $('#types').querySelectorAll('.type-btn').forEach(b => b.onclick = () => {
    if (state.kind === b.dataset.id) return;
    state.kind = b.dataset.id; store.kind = state.kind; save();
    renderTypes(); renderForm(); requestBuild(true);
  });
}

function fieldHtml(f, v) {
  const id = 'f_' + f.k;
  const lab = `<label for="${id}">${f.l}${f.s ? `<small>${f.s}</small>` : ''}</label>`;
  if (f.t === 'bool')
    return `<div class="field bool" data-k="${f.k}">${lab}<input id="${id}" type="checkbox" ${v ? 'checked' : ''}></div>`;
  if (f.t === 'sel')
    return `<div class="field" data-k="${f.k}">${lab}<div class="ctl"><select id="${id}">${f.opts.map(([o, n]) =>
      `<option value="${o}" ${String(v) === String(o) ? 'selected' : ''}>${n}</option>`).join('')}</select></div></div>`;
  const list = f.list ? `list="dl_${f.k}"` : '';
  const dl = f.list ? `<datalist id="dl_${f.k}">${f.list.map(x => `<option value="${x}">`).join('')}</datalist>` : '';
  return `<div class="field" data-k="${f.k}">${lab}<div class="ctl"><input id="${id}" type="number" value="${v}"
    ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} step="${f.step ?? 'any'}" ${list}>
    ${f.u ? `<span class="unit">${f.u}</span>` : ''}</div>${dl}</div>`;
}

function renderForm() {
  const t = TYPES.find(x => x.id === state.kind);
  if (t.custom) return renderReducer();
  const v = vals();
  const form = $('#form');
  form.innerHTML = t.sections.map((sec, i) =>
    `<details class="sec" ${sec.collapsed ? '' : 'open'}><summary>${sec.title}</summary>
      ${sec.fields.map(f => fieldHtml(f, v[f.k])).join('')}</details>`).join('');
  const all = t.sections.flatMap(s => s.fields);
  const applyShow = () => all.forEach(f => {
    if (!f.show) return;
    const el = form.querySelector(`.field[data-k="${f.k}"]`);
    if (el) el.style.display = f.show(v) ? '' : 'none';
  });
  applyShow();
  all.forEach(f => {
    const el = $('#f_' + f.k);
    const ev = f.t === 'bool' || f.t === 'sel' ? 'change' : 'input';
    el.addEventListener(ev, () => {
      let val;
      if (f.t === 'bool') val = el.checked;
      else if (f.t === 'sel') val = el.value;
      else {
        val = parseFloat(el.value);
        const bad = !Number.isFinite(val) || (f.min != null && val < f.min) || (f.max != null && val > f.max);
        el.closest('.field').classList.toggle('invalid', bad);
        if (bad) return;
        if (f.int) val = Math.round(val);
      }
      v[f.k] = val; store.vals = state.vals; save();
      applyShow(); requestBuild();
    });
  });
}

/* ---------- Redüktör paneli ---------- */

const GTYPES = [['duz', 'Düz'], ['helisel', 'Helisel'], ['konik', 'Konik'], ['worm', 'Sonsuz vida']];

function renderReducer() {
  const v = vals();
  const mats = state.meta.materials;
  const k0 = Object.entries(state.meta.k0 || {});
  const gen = [
    { k: 'P_in', l: 'Giriş gücü P', u: 'kW', d: 0.25, min: 0.001, step: 0.05 },
    { k: 'n_in', l: 'Giriş devri n', u: 'd/dk', d: 1500, min: 1, step: 10 },
    { k: 'i_total', l: 'Toplam oran i', d: 9, min: 1.01, step: 0.1 },
    { k: 'Lh', l: 'Hedef ömür Lh', u: 'saat', d: 10000, min: 100, step: 500 },
    { k: 'S', l: 'Emniyet katsayısı S', d: 1.5, min: 1, max: 5, step: 0.1 },
    { k: 'backlash', l: 'Boşluk j', u: 'mm', d: 0.15, min: 0, max: 2, step: 0.05 },
    { k: 'bed', l: 'Baskı yatağı', u: 'mm', d: 220, min: 50, step: 10 },
    { k: 'lubricated', l: 'Gresli (yağlamalı)', t: 'bool', d: false },
    { k: 'bore_type', l: 'Göbek bağlantısı', t: 'sel', d: 'kama', opts: [['kama', 'Kamalı (DIN 6885)'], ['daire', 'Dairesel'], ['dflat', 'D-kesit'], ['altigen', 'Altıgen']] },
  ];
  const stageHtml = (s, i) => `
    <div class="stage" data-i="${i}">
      <div class="stage-head"><span>Kademe ${i + 1}</span>${v.stages.length > 1 ? `<button data-del="${i}" title="Kaldır">✕</button>` : ''}</div>
      ${fieldHtml({ k: `s${i}_gtype`, l: 'Tip', t: 'sel', opts: GTYPES }, s.gtype)}
      ${fieldHtml({ k: `s${i}_material`, l: 'Malzeme', t: 'sel', opts: mats.map(m => [m, m]) }, s.material)}
      ${fieldHtml({ k: `s${i}_i_stage`, l: 'Kademe oranı i', min: 1, step: 0.05 }, s.i_stage)}
      ${s.gtype === 'helisel' ? fieldHtml({ k: `s${i}_beta`, l: 'Helis açısı β', u: '°', min: 0, max: 45, step: 1 }, s.beta) : ''}
      ${s.gtype === 'worm' ? fieldHtml({ k: `s${i}_z1`, l: 'Ağız sayısı z₁', min: 1, max: 6, step: 1 }, s.z1)
        + fieldHtml({ k: `s${i}_q`, l: 'Çap katsayısı q', min: 5, max: 20, step: 0.5 }, s.q)
        : fieldHtml({ k: `s${i}_z1_gear`, l: 'Pinyon z₁', s: 'boş = otomatik', min: 6, max: 100, step: 1 }, s.z1_gear ?? '')}
      ${k0.length ? fieldHtml({ k: `s${i}_K0`, l: 'İşletme faktörü K₀', t: 'sel', opts: k0.map(([n, x]) => [x, `${x} — ${n.split(' (')[0]}`]) }, s.K0) : ''}
    </div>`;
  $('#form').innerHTML = `
    <details class="sec" open><summary>Giriş ve genel</summary>${gen.map(f => fieldHtml(f, v[f.k] ?? f.d)).join('')}</details>
    <details class="sec" open><summary>Kademeler</summary>
      <div id="stageList">${v.stages.map(stageHtml).join('')}</div>
      <div class="row-btns">
        ${v.stages.length < 3 ? '<button class="btn sm" id="addStage">+ Kademe ekle</button>' : ''}
        <button class="btn sm" id="evenSplit">Oranı eşit dağıt</button>
      </div>
    </details>
    <details class="sec" open><summary>Tasarım arama motoru</summary>
      ${fieldHtml({ k: 'objective', l: 'Amaç', t: 'sel', opts: [['koaksiyel', 'Eş eksenli'], ['min_hacim', 'En küçük hacim'], ['max_verim', 'En yüksek verim'], ['oran_hassas', 'Oran hassasiyeti']] }, v.objective)}
      <div class="row-btns"><button class="btn sm" id="runSearch">En iyi 5 tasarımı ara</button></div>
      <div class="search-res" id="searchRes"></div>
    </details>
    <p class="hint">Hesap: <b>hesap/</b> paketi (Akkurt / DIN). Geometri: <b>py_gearworks</b>.
      Miller ve göbek delikleri hesaplanan mil çaplarından oluşturulur.</p>`;

  const bind = (k, fn) => {
    const el = $('#f_' + k); if (!el) return;
    el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', () => fn(el));
  };
  const num = el => { const x = parseFloat(el.value); const ok = Number.isFinite(x); el.closest('.field')?.classList.toggle('invalid', !ok); return ok ? x : null; };
  const commit = (rerender) => { store.vals = state.vals; save(); if (rerender) renderReducer(); requestBuild(); };
  gen.forEach(f => bind(f.k, el => {
    const x = f.t === 'bool' ? el.checked : f.t === 'sel' ? el.value : num(el);
    if (x === null) return; v[f.k] = x; commit(false);
  }));
  bind('objective', el => { v.objective = el.value; store.vals = state.vals; save(); });
  v.stages.forEach((s, i) => {
    ['gtype', 'material', 'K0'].forEach(k => bind(`s${i}_${k}`, el => {
      s[k] = k === 'K0' ? parseFloat(el.value) : el.value; commit(k === 'gtype');
    }));
    ['i_stage', 'beta', 'z1', 'q'].forEach(k => bind(`s${i}_${k}`, el => { const x = num(el); if (x === null) return; s[k] = x; commit(false); }));
    bind(`s${i}_z1_gear`, el => { s.z1_gear = el.value === '' ? '' : Math.round(parseFloat(el.value)); commit(false); });
  });
  $('#form').querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
    v.stages.splice(+b.dataset.del, 1); commit(true);
  });
  const add = $('#addStage');
  if (add) add.onclick = () => { v.stages.push({ ...v.stages[v.stages.length - 1] }); commit(true); };
  $('#evenSplit').onclick = () => {
    const per = Math.pow(v.i_total, 1 / v.stages.length);
    v.stages.forEach(s => s.i_stage = +per.toFixed(3)); commit(true);
  };
  $('#runSearch').onclick = runSearch;
}

async function runSearch() {
  const v = vals('reduktor');
  const box = $('#searchRes');
  box.innerHTML = '<div class="hint">Aranıyor… (binlerce kombinasyon hesaplanıyor)</div>';
  try {
    const r = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ params: reducerParams(v) }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Arama başarısız');
    if (!j.best.length) { box.innerHTML = '<div class="hint">Kısıtları sağlayan tasarım bulunamadı (malzeme/oranı değiştirin).</div>'; return; }
    box.innerHTML = j.best.map((b, i) => `<div class="search-item"><div><b>#${i + 1}</b> i=${b.i_real.toFixed(3)} · η=${(b.eta * 100).toFixed(1)}% · V=${b.volume.toFixed(0)} cm³<br>
      <span class="hint">z: ${b.z_list.map(z => z.join('/')).join(' · ')} — m: ${b.mn_list.join(', ')} — eksen farkı ${b.coax_err.toFixed(1)} mm</span></div>
      <button class="btn sm" data-apply="${i}">Uygula</button></div>`).join('');
    box.querySelectorAll('[data-apply]').forEach(btn => btn.onclick = () => {
      const cfg = j.best[+btn.dataset.apply].cfg;
      v.stages.forEach((s, k) => {
        const c = cfg.stages[k]; if (!c) return;
        s.i_stage = +(+c.i_stage).toFixed(4);
        if (c.z1_gear) s.z1_gear = c.z1_gear;
        if (c.beta != null) s.beta = c.beta;
      });
      store.vals = state.vals; save(); renderReducer(); requestBuild(true);
    });
  } catch (e) { box.innerHTML = `<div class="hint bad">${e.message}</div>`; }
}

function reducerParams(v) {
  const p = { ...v };
  delete p.objective;
  p.stages = v.stages.map(s => {
    const o = { gtype: s.gtype, material: s.material, i_stage: s.i_stage, K0: s.K0 };
    if (s.gtype === 'helisel') o.beta = s.beta;
    if (s.gtype === 'worm') { o.z1 = s.z1; o.q = s.q; }
    else if (s.z1_gear !== '' && s.z1_gear != null) o.z1_gear = s.z1_gear;
    return o;
  });
  p.objective = v.objective;
  return p;
}

/* ================================================================
   3B görüntüleyici
   ================================================================ */

const canvas = $('#canvas');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 1e6);
camera.up.set(0, 0, 1);
camera.position.set(80, -110, 90);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.12;

scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4150, 1.6));
const key = new THREE.DirectionalLight(0xffffff, 1.9); key.position.set(1, -1.4, 2.2); scene.add(key);
const fill = new THREE.DirectionalLight(0xbfd4ff, 0.7); fill.position.set(-1.5, 1, -0.4); scene.add(fill);

let grid = null;
const model = new THREE.Group(); scene.add(model);
let meshes = [];        // {group, mesh, edges, anim, visible}
let showEdges = true, wire = false, playing = false, theta = 0, phase = 0, animMode = 'rot', oscAmp = 1;

function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function applyThemeToScene() {
  scene.background = new THREE.Color(cssVar('--view'));
  if (grid) { grid.material.color = new THREE.Color(cssVar('--grid')); }
  meshes.forEach(m => m.edges.material.color.set(isLight() ? 0x2b2f36 : 0x0b0d10));
}
const isLight = () => document.documentElement.dataset.theme === 'light';

function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / Math.max(r.height, 1);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas.parentElement);

function b64ToArr(b64, Type) {
  const bin = atob(b64); const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Type(u8.buffer);
}

function setModel(data, refit) {
  meshes.forEach(m => { m.mesh.geometry.dispose(); m.mesh.material.dispose(); m.edges.geometry.dispose(); m.edges.material.dispose(); });
  model.clear(); meshes = [];
  data.parts.forEach(p => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(b64ToArr(p.pos, Float32Array), 3));
    g.setIndex(new THREE.BufferAttribute(b64ToArr(p.idx, Uint32Array), 1));
    g.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: p.color, metalness: 0.2, roughness: 0.48,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, side: THREE.DoubleSide, wireframe: wire });
    const mesh = new THREE.Mesh(g, mat);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(g, 28),
      new THREE.LineBasicMaterial({ color: isLight() ? 0x2b2f36 : 0x0b0d10, transparent: true, opacity: 0.55 }));
    edges.visible = showEdges;
    const grp = new THREE.Group(); grp.add(mesh, edges); grp.matrixAutoUpdate = false;
    model.add(grp);
    meshes.push({ group: grp, mesh, edges, anim: p.anim, name: p.name, color: p.color, visible: true });
  });
  animMode = data.anim_mode || 'rot';
  oscAmp = data.summary?.osc_amp || 1;
  theta = 0; phase = 0;
  applyAnim();
  updateGrid();
  if (refit) fit();
  renderChips();
}

function updateGrid() {
  if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
  const box = new THREE.Box3().setFromObject(model);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.y, 20) * 3;
  const step = Math.pow(10, Math.floor(Math.log10(span / 8)));
  const n = Math.ceil(span / step);
  grid = new THREE.GridHelper(n * step, n, cssVar('--grid'), cssVar('--grid'));
  grid.rotation.x = Math.PI / 2;
  const c = box.getCenter(new THREE.Vector3());
  grid.position.set(c.x, c.y, box.min.z - 0.02);
  grid.material.transparent = true; grid.material.opacity = 0.8;
  scene.add(grid);
}

function fit(top = false) {
  const box = new THREE.Box3().setFromObject(model);
  if (box.isEmpty()) return;
  const c = box.getCenter(new THREE.Vector3());
  const r = box.getBoundingSphere(new THREE.Sphere()).radius;
  const vHalf = THREE.MathUtils.degToRad(camera.fov / 2);
  const hHalf = Math.atan(Math.tan(vHalf) * camera.aspect);
  const dist = r / Math.sin(Math.min(vHalf, hHalf)) * 1.05;
  const dir = top ? new THREE.Vector3(0, -0.001, 1) : new THREE.Vector3(0.9, -1.35, 1.0);
  camera.position.copy(c).add(dir.normalize().multiplyScalar(dist));
  camera.near = dist / 200; camera.far = dist * 50; camera.updateProjectionMatrix();
  controls.target.copy(c); controls.update();
}

const _m1 = new THREE.Matrix4(), _m2 = new THREE.Matrix4(), _v = new THREE.Vector3();
function rotAbout(out, o, a, ang) {
  _v.set(a[0], a[1], a[2]).normalize();
  out.makeTranslation(o[0], o[1], o[2]);
  out.multiply(_m1.makeRotationAxis(_v, ang));
  out.multiply(_m2.makeTranslation(-o[0], -o[1], -o[2]));
  return out;
}
function applyAnim() {
  const th = animMode === 'osc' ? oscAmp * Math.sin(phase / Math.max(oscAmp, 0.3)) : theta;
  meshes.forEach(m => {
    const a = m.anim || {}; const M = m.group.matrix;
    M.identity();
    if (a.type === 'rot') {
      if (a.carrier) rotAbout(M, [0, 0, 0], [0, 0, 1], a.carrier * th);
      const R = rotAbout(new THREE.Matrix4(), a.origin, a.axis, a.ratio * th);
      M.multiply(R);
    } else if (a.type === 'lin') {
      M.makeTranslation(a.vel[0] * th, a.vel[1] * th, a.vel[2] * th);
    }
    m.group.matrixWorldNeedsUpdate = true;
  });
}

let last = performance.now();
function loop(now) {
  const dt = Math.min((now - last) / 1000, 0.1); last = now;
  if (playing) {
    const sp = parseFloat($('#speed').value);
    theta += dt * sp; phase += dt * sp;
    applyAnim();
  }
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}

function renderChips() {
  $('#partsList').innerHTML = meshes.map((m, i) =>
    `<div class="chip${m.visible ? '' : ' off'}" data-i="${i}" title="Göster / gizle"><span class="sw" style="background:${m.color}"></span>${m.name}</div>`).join('');
  $('#partsList').querySelectorAll('.chip').forEach(c => c.onclick = () => {
    const m = meshes[+c.dataset.i]; m.visible = !m.visible; m.group.visible = m.visible; renderChips();
  });
}

/* ================================================================
   Sunucu ile iletişim
   ================================================================ */

let buildTimer = null;
function requestBuild(now = false) {
  clearTimeout(buildTimer);
  if (!now && !$('#auto').checked) { setStatus('Değişiklik var — “Oluştur”a basın'); return; }
  buildTimer = setTimeout(doBuild, now ? 0 : 650);
}

function setStatus(t) { $('#status').textContent = t; }
function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.hidden = !msg;
  clearTimeout(toast._t); if (msg) toast._t = setTimeout(() => el.hidden = true, 7000);
}

let lastKind = null, loadingTimer = null;
async function doBuild() {
  const seq = ++state.seq;
  const kind = state.kind;
  const v = vals(kind);
  const params = kind === 'reduktor' ? reducerParams(v) : v;
  const t0 = performance.now();
  $('#loading').hidden = false;
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => { $('#loadingText').textContent = `Oluşturuluyor… ${((performance.now() - t0) / 1000).toFixed(1)} sn`; }, 100);
  setStatus('Oluşturuluyor…');
  $('#btnBuild').disabled = true;
  try {
    const r = await fetch('/api/build', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, params }) });
    const j = await r.json();
    if (seq !== state.seq) return;
    if (!r.ok) throw new Error(j.error || 'Hata');
    state.current = j;
    setModel(j, kind !== lastKind);
    lastKind = kind;
    renderInfo(j);
    if (Number.isFinite(state.fixedTheta)) { theta = phase = state.fixedTheta; applyAnim(); }
    if (state.wantTab && j.report) { showTab(state.wantTab); state.wantTab = null; }
    toast('');
    setStatus(`Oluşturuldu · ${(j.ms / 1000).toFixed(1)} sn · ${j.parts.length} parça`);
  } catch (e) {
    if (seq !== state.seq) return;
    toast(e.message); setStatus('Hata');
  } finally {
    if (seq === state.seq) { $('#loading').hidden = true; clearInterval(loadingTimer); $('#btnBuild').disabled = false; }
  }
}

function fmtVal(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : (Math.abs(v) >= 100 ? v.toFixed(2) : +v.toFixed(6) + '');
  if (typeof v === 'boolean') return v ? 'EVET' : 'HAYIR';
  return String(v);
}
function kvHtml(o, skip = []) {
  return Object.entries(o).filter(([k, v]) => !skip.includes(k) && typeof v !== 'object').map(([k, v]) =>
    `<div class="k">${LABELS[k] || k}</div><div class="v">${fmtVal(v)}${UNITS[k] ? ' ' + UNITS[k] : ''}</div>`).join('');
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function renderInfo(j) {
  const s = j.summary || {};
  const sk = kvHtml(s, ['osc_amp', 'kademeler']);
  $('#summaryCard').hidden = !sk; $('#summary').innerHTML = sk;
  $('#warnCard').hidden = !j.warnings.length;
  $('#warnings').innerHTML = j.warnings.map(w => `<li>${esc(w)}</li>`).join('');
  const st = s.kademeler;
  $('#stageCard').hidden = !st;
  if (st) {
    $('#stages').innerHTML = `<table class="st"><tr><th>K</th><th>Tip</th><th>z₁/z₂</th><th>m</th><th>b</th><th>a</th><th>σ/σem</th><th>εα</th></tr>
      ${st.map(r => `<tr><td>${r.k}</td><td>${r.tip}</td><td>${r.z1}/${r.z2}</td><td>${r.m}</td><td>${r.b}</td><td>${r.a}</td>
      <td class="${r.ok ? 'ok' : 'bad'}">${r['σ']}/${r['σ_em']}</td><td>${r['εα']}</td></tr>`).join('')}</table>`;
  }
  $('#partInfo').innerHTML = j.parts.map(p => Object.keys(p.info || {}).length ? `<div class="part-block">
      <div class="part-title"><span class="sw" style="background:${p.color}"></span>${esc(p.name)}</div>
      <div class="kv">${kvHtml(p.info)}</div></div>` : '').join('');
  $('#expPart').innerHTML = '<option value="all">Tüm parçalar</option>' +
    j.parts.map((p, i) => `<option value="${i}">${esc(p.name)}</option>`).join('');
  const hasRep = !!j.report;
  $('#tabRapor').hidden = !hasRep;
  $('#tabGrafik').hidden = !hasRep;
  $('#report').textContent = j.report || '';
  if (!hasRep) showTab('ozet'); else setupSweep(j);
}

function showTab(t) {
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  ['ozet', 'grafik', 'rapor'].forEach(n => { $('#pane-' + n).hidden = t !== n; });
  if (t === 'grafik' && sweep.data) drawSweep();   // panel görünür olunca genişliği doğru ölç
}

/* ================================================================
   Duyarlılık grafikleri (küçük çoklu grafikler, ortak x ekseni)
   ================================================================ */

const SWEEP_PARAMS = {
  duz: [['x1', 'Profil kaydırma x₁'], ['i_stage', 'Kademe oranı i']],
  helisel: [['x1', 'Profil kaydırma x₁'], ['beta', 'Helis açısı β'], ['i_stage', 'Kademe oranı i']],
  konik: [['phi_m', 'Genişlik oranı φm'], ['i_stage', 'Kademe oranı i']],
  worm: [['q', 'Çap katsayısı q']],
};
const sweep = { data: null, seq: 0, scales: [] };

function setupSweep(j) {
  const st = j.summary?.kademeler || [];
  const sel = $('#swStage');
  const prev = sel.value;
  sel.innerHTML = st.map((r, i) => `<option value="${i}">Kademe ${r.k} — ${r.tip}</option>`).join('');
  if (prev && +prev < st.length) sel.value = prev;
  fillParams(); loadSweep();
}
function fillParams() {
  const st = state.current?.summary?.kademeler || [];
  const g = st[+$('#swStage').value]?.tip || 'duz';
  const opts = SWEEP_PARAMS[g] || [];
  const sel = $('#swParam'); const prev = sel.value;
  sel.innerHTML = opts.map(([id, l]) => `<option value="${id}">${l}</option>`).join('');
  if (opts.some(o => o[0] === prev)) sel.value = prev;
}
async function loadSweep() {
  const seq = ++sweep.seq;
  $('#swReadout').textContent = 'Hesaplanıyor…';
  try {
    const r = await fetch('/api/sweep', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params: reducerParams(vals('reduktor')), stage: +$('#swStage').value, param: $('#swParam').value }) });
    const j = await r.json();
    if (seq !== sweep.seq) return;
    if (!r.ok) throw new Error(j.error || 'Tarama başarısız');
    sweep.data = j;
    drawSweep(); readout(null);
  } catch (e) { $('#swReadout').textContent = e.message; }
}
$('#swStage').onchange = () => { fillParams(); loadSweep(); };
$('#swParam').onchange = loadSweep;
$('#swTable').onclick = () => {
  const box = $('#swTableBox'); box.hidden = !box.hidden;
  $('#swTable').textContent = box.hidden ? 'Tablo olarak göster' : 'Tabloyu gizle';
  if (!box.hidden) renderSweepTable();
};

function niceTicks(lo, hi, n = 4) {
  const span = hi - lo || Math.abs(hi) || 1;
  const step0 = span / n, p = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(k => k * p).find(k => k >= step0);
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
  const t = []; for (let v = a; v <= b + step * 1e-6; v += step) t.push(+v.toFixed(10));
  return t;
}
const fmtN = v => v == null ? '—' : Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : (+v.toFixed(3)).toString();
const shortName = n => n.split(' ').slice(-1)[0];

function drawSweep() {
  const d = sweep.data; if (!d) return;
  const box = $('#charts');
  const W = Math.max(240, box.clientWidth - 18), H = 132, m = { l: 40, r: 8, t: 10, b: 22 };
  const xs = d.x, x0 = xs[0], x1 = xs[xs.length - 1];
  const X = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r);
  const xt = niceTicks(x0, x1, 4).filter(v => v >= x0 - 1e-9 && v <= x1 + 1e-9);
  const ci = xs.reduce((b, v, i) => Math.abs(v - d.current) < Math.abs(xs[b] - d.current) ? i : b, 0);
  sweep.scales = [];
  box.innerHTML = d.panels.map((p, pi) => {
    const vals = p.y.filter(v => v != null).concat((p.lim || []).filter(v => v != null));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (lo >= 0 && lo < (hi - lo) * 0.6) lo = 0;            // pozitif büyüklüklerde sıfırdan başla
    const yt = niceTicks(lo, hi, 3); lo = yt[0]; hi = yt[yt.length - 1];
    const Y = v => m.t + (1 - (v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
    sweep.scales[pi] = Y;
    const path = arr => { let s = '', pen = false; arr.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      s += `${pen ? 'L' : 'M'}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; }); return s; };
    // uygun olmayan bölge: sınır çizgisi ile grafik kenarı arası (soluk kırmızı)
    let bad = '';
    if (p.lim) {
      const edge = p.kind === 'max' ? hi : lo;
      const pts = p.lim.map((v, i) => v == null ? null : [X(xs[i]).toFixed(1), Y(v).toFixed(1)]).filter(Boolean);
      if (pts.length) bad = `<path class="badzone" d="M${pts.map(q => q.join(',')).join('L')}L${pts[pts.length - 1][0]},${Y(edge)}L${pts[0][0]},${Y(edge)}Z"/>`;
    }
    let status = '';
    if (p.lim && p.y[ci] != null && p.lim[ci] != null) {
      const ok = p.kind === 'max' ? p.y[ci] <= p.lim[ci] : p.y[ci] >= p.lim[ci];
      status = `<span class="st ${ok ? 'ok' : 'bad'}">${ok ? '✓ mevcut tasarım sınır içinde' : '✕ mevcut tasarım sınır dışında'}</span>`;
    }
    const firstLim = p.lim ? p.lim.map((v, i) => [v, i]).find(q => q[0] != null) : null;
    return `<div class="chart" data-p="${pi}">
      <div class="chart-title"><span>${p.name}${p.unit ? ` <span class="tick">(${p.unit})</span>` : ''}</span></div>
      ${status ? `<div class="chart-title">${status}</div>` : ''}
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${p.name} — ${d.xlabel} taraması">
        ${yt.map(v => `<line class="ax" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" opacity=".5"/>
          <text class="tick" x="${m.l - 5}" y="${Y(v) + 3}" text-anchor="end">${fmtN(v)}</text>`).join('')}
        ${xt.map(v => `<text class="tick" x="${X(v)}" y="${H - 6}" text-anchor="middle">${fmtN(v)}</text>`).join('')}
        ${bad}
        ${p.lim ? `<path class="lim" d="${path(p.lim)}"/>` : ''}
        ${firstLim ? `<text class="lbl" x="${m.l + 4}" y="${Y(firstLim[0]) + (p.kind === 'max' ? -5 : 12)}">${p.limit_label}</text>` : ''}
        <line class="cur" x1="${X(d.current)}" x2="${X(d.current)}" y1="${m.t}" y2="${H - m.b}"/>
        ${pi === 0 ? `<text class="lbl" x="${X(d.current) + 4}" y="${m.t + 8}">mevcut</text>` : ''}
        <path class="line" d="${path(p.y)}"/>
        <g class="hov" visibility="hidden"><line class="xh" y1="${m.t}" y2="${H - m.b}"/><circle class="dot" r="4.5"/></g>
        <rect class="hit" x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H - m.b}" fill="transparent"/>
      </svg></div>`;
  }).join('');
  sweep.X = X; sweep.W = W;
  box.querySelectorAll('.chart').forEach(c => {
    const hit = c.querySelector('.hit');
    hit.addEventListener('pointermove', e => {
      const r = c.querySelector('svg').getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width * W;
      hoverAt(xs.reduce((b, v, k) => Math.abs(X(v) - px) < Math.abs(X(xs[b]) - px) ? k : b, 0));
    });
    hit.addEventListener('pointerleave', () => hoverAt(null));
  });
  if (!$('#swTableBox').hidden) renderSweepTable();
}

function hoverAt(i) {
  const d = sweep.data;
  $('#charts').querySelectorAll('.chart').forEach(c => {
    const pi = +c.dataset.p, p = d.panels[pi], g = c.querySelector('.hov');
    if (i == null || p.y[i] == null) { g.setAttribute('visibility', 'hidden'); return; }
    const x = sweep.X(d.x[i]), y = sweep.scales[pi](p.y[i]);
    const xh = g.querySelector('.xh'); xh.setAttribute('x1', x); xh.setAttribute('x2', x);
    const dot = g.querySelector('.dot'); dot.setAttribute('cx', x); dot.setAttribute('cy', y);
    g.setAttribute('visibility', 'visible');
  });
  readout(i);
}

function readout(i) {
  const d = sweep.data; if (!d) return;
  const el = $('#swReadout');
  if (i == null) {
    el.innerHTML = `Kademe ${d.stage} · ${d.material} · <b>${d.xlabel}</b> taranıyor (mevcut: ${fmtN(d.current)}${d.xunit}). Değerler için grafiğin üzerine gelin.`;
    return;
  }
  el.innerHTML = `<b>${d.xlabel} = ${fmtN(d.x[i])}${d.xunit}</b><br>` + d.panels.map(p =>
    `${shortName(p.name)} = <b>${fmtN(p.y[i])}</b>${p.unit ? ' ' + p.unit : ''}`).join(' · ');
}

function renderSweepTable() {
  const d = sweep.data; if (!d) return;
  $('#swTableBox').innerHTML = `<table class="sw-table"><tr><th>${shortName(d.xlabel)}</th>${d.panels.map(p =>
    `<th>${shortName(p.name)}${p.unit ? ` (${p.unit})` : ''}</th>`).join('')}</tr>
    ${d.x.map((x, i) => `<tr><td>${fmtN(x)}</td>${d.panels.map(p => `<td>${fmtN(p.y[i])}</td>`).join('')}</tr>`).join('')}</table>`;
}
new ResizeObserver(() => { if (sweep.data && !$('#pane-grafik').hidden) drawSweep(); }).observe($('#info'));

async function download(url) {
  setStatus('Dışa aktarılıyor…');
  try {
    const r = await fetch(url);
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || 'Dışa aktarma başarısız'); }
    const cd = r.headers.get('Content-Disposition') || '';
    const name = (cd.match(/filename="([^"]+)"/) || [])[1] || 'dosya';
    const blob = await r.blob();
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    setStatus(`İndirildi: ${name}`);
  } catch (e) { toast(e.message); setStatus('Hata'); }
}

/* ================================================================
   Olaylar
   ================================================================ */

$('#btnBuild').onclick = () => requestBuild(true);
$('#auto').checked = store.auto ?? true;
$('#auto').onchange = () => { store.auto = $('#auto').checked; save(); };
document.querySelectorAll('.exp-btns .btn').forEach(b => b.onclick = () => {
  if (!state.current) return toast('Önce model oluşturun');
  download(`/api/export/${state.current.id}?fmt=${b.dataset.fmt}&part=${$('#expPart').value}`);
});
$('#btnReportDl').onclick = () => state.current && download(`/api/report/${state.current.id}`);
document.querySelectorAll('.tab').forEach(b => b.onclick = () => showTab(b.dataset.tab));

const setPlay = p => { playing = p; $('#btnPlay').textContent = p ? '❚❚' : '▶'; $('#btnPlay').classList.toggle('on', p); };
$('#btnPlay').onclick = () => setPlay(!playing);
$('#btnFit').onclick = () => fit();
$('#btnTop').onclick = () => fit(true);
$('#btnEdges').onclick = () => { showEdges = !showEdges; $('#btnEdges').classList.toggle('on', showEdges); meshes.forEach(m => m.edges.visible = showEdges); };
$('#btnWire').onclick = () => { wire = !wire; $('#btnWire').classList.toggle('on', wire); meshes.forEach(m => m.mesh.material.wireframe = wire); };
$('#btnShot').onclick = () => {
  renderer.render(scene, camera);
  const a = document.createElement('a'); a.href = renderer.domElement.toDataURL('image/png');
  a.download = `cark_${state.kind}.png`; a.click();
};
window.addEventListener('keydown', e => {
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); setPlay(!playing); }
  if (e.key === 'f' || e.key === 'F') fit();
});

const setTheme = t => { document.documentElement.dataset.theme = t; store.theme = t; save(); applyThemeToScene(); };
$('#btnTheme').onclick = () => setTheme(isLight() ? 'dark' : 'light');
document.documentElement.dataset.theme = store.theme || 'dark';

/* ================================================================
   Başlat
   ================================================================ */

(async function init() {
  try {
    const r = await fetch('/api/meta'); const j = await r.json();
    state.meta.materials = j.materials; state.meta.k0 = j.k0;
  } catch { /* varsayılanlar */ }
  // ?tip=helisel&oynat=1&tema=light -> doğrudan o sekme (paylaşılabilir link)
  const q = new URLSearchParams(location.search);
  if (q.get('tip') && TYPES.some(t => t.id === q.get('tip'))) state.kind = q.get('tip');
  if (q.get('tema')) document.documentElement.dataset.theme = q.get('tema');
  if (q.get('oynat') === '1') setPlay(true);
  if (q.get('sekme')) state.wantTab = q.get('sekme');
  if (q.get('aci') !== null) state.fixedTheta = parseFloat(q.get('aci'));
  resize(); applyThemeToScene();
  renderTypes(); renderForm();
  requestAnimationFrame(loop);
  requestBuild(true);
})();
