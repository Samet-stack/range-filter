const {test} = require('node:test');
const assert = require('node:assert/strict');
const {KronosOverlay} = require('./static/kronos-overlay.js');

const selection = {sym:'ETH', tf:'1h', src:'hl_spot', market:'Hyperliquid spot UETH/USDC', model:'original', bar:100};
function fixture() {
  const pending = [], renders = [], statuses = [];
  let displayed = 0;
  const overlay = new KronosOverlay({
    request: (s, signal) => new Promise((resolve, reject) => pending.push({s, signal, resolve, reject})),
    render: data => { renders.push(data); displayed += 51; },
    clear: () => { displayed = 0; },
    status: (...args) => statuses.push(args),
    now: () => 1000,
  });
  const result = s => ({sym:s.sym, tf:s.tf, source:s.src, src:s.market, model:s.model, start:{time:s.bar}, horizon:12, model_label:s.model});
  return {overlay, pending, renders, statuses, result, displayed:() => displayed};
}

test('repeated chart polls cannot duplicate a forecast', async () => {
  const f = fixture();
  const first = f.overlay.sync(selection);
  for (let i=0; i<5; i++) f.overlay.sync(selection);
  assert.equal(f.pending.length, 1);
  f.pending[0].resolve(f.result(selection));
  await first;
  await f.overlay.sync(selection);
  assert.equal(f.pending.length, 1);
  assert.equal(f.displayed(), 51);
});

test('old market response arriving last never replaces current forecast', async () => {
  const f = fixture();
  const old = f.overlay.sync(selection);
  const next = {...selection, sym:'BTC', model:'crypto-v1'};
  const current = f.overlay.sync(next);
  assert.equal(f.pending[0].signal.aborted, true);
  f.pending[1].resolve(f.result(next));
  await current;
  f.pending[0].resolve(f.result(selection));
  await old;
  assert.equal(f.renders.length, 1);
  assert.equal(f.renders[0].sym, 'BTC');
  assert.equal(f.displayed(), 51);
});

test('switching off during calculation keeps chart empty', async () => {
  const f = fixture();
  const old = f.overlay.sync(selection);
  await f.overlay.sync(null);
  f.pending[0].resolve(f.result(selection));
  await old;
  assert.equal(f.displayed(), 0);
  assert.equal(f.renders.length, 0);
});

test('failed calculations show an error and back off instead of polling the GPU', async () => {
  const f = fixture();
  const current = f.overlay.sync(selection);
  f.pending[0].reject(new Error('GPU occupé'));
  await current;
  await f.overlay.sync(selection);
  assert.equal(f.pending.length, 1);
  assert.deepEqual(f.statuses.at(-1), ['error', 'GPU occupé']);
});

test('a different last closed candle is rejected, then the new chart can request it', async () => {
  const f = fixture();
  const current = f.overlay.sync(selection);
  f.pending[0].resolve({...f.result(selection), start:{time:101}});
  await current;
  assert.equal(f.displayed(), 0);
  const next = {...selection, bar:101};
  const p = f.overlay.sync(next);
  f.pending[1].resolve(f.result(next));
  await p;
  assert.equal(f.displayed(), 51);
});

test('a spot/perpetual fallback cannot be drawn over the other market', async () => {
  const f = fixture();
  const current = f.overlay.sync(selection);
  f.pending[0].resolve({...f.result(selection), src:'Hyperliquid perp (pas de spot)'});
  await current;
  assert.equal(f.renders.length, 0);
  assert.equal(f.statuses.at(-1)[0], 'error');
});
