const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const api = vm.runInNewContext(fs.readFileSync(path.join(root, 'black-friday.js'), 'utf8') + '\nblackFriday2026', {URL});
const seasonal = JSON.parse(fs.readFileSync(path.join(root, 'data/black-friday-2026.json')));
const approved = JSON.parse(fs.readFileSync(path.join(root, 'data/approved.json')));

test('vendor dates, undated end of season, and UK timing', () => {
  const onlySecurity = seasonal.offers.find(d => d.provider === 'OnlySecurity');
  assert.equal(api.status(onlySecurity, '2026-11-22', Date.parse('2026-11-22T23:59:00Z')), 'upcoming');
  assert.equal(api.status(onlySecurity, '2026-11-22', Date.parse('2026-11-23T00:00:00Z')), 'live');
  assert.equal(api.status(onlySecurity, '2026-11-30', Date.parse('2026-12-01T00:00:00Z')), 'closed');
  assert.equal(api.status({}, '2026-11-30'), 'live');
  assert.equal(api.status({}, '2026-12-01'), 'closed');
  assert.equal(api.status({deadline:'2027-01-04'}, '2026-12-01'), 'live');
});

test('existing deal keeps its saved ID and supplied codes while unconfirmed leads stay out', () => {
  const catalog = api.merge(approved.offers, seasonal.offers);
  const practical = catalog.filter(x => x.provider === 'Practical DevSecOps' && x.blackFriday);
  const unique = new Set(catalog.map(x => api.urlKey(x.source)));
  assert.equal(unique.size, catalog.length);
  assert.equal(practical.length, 1);
  assert.equal(practical[0].id, 'curated-practical-devsecops-2026');
  assert(catalog.some(x => x.id === 'curated-isa-black-friday-2026' && x.blackFriday));
  assert(catalog.some(x => x.provider === 'Just Hacking Training' && x.code === 'BFF25'));
  assert(!catalog.some(x => x.blackFriday && x.verification === 'reported'));
});
