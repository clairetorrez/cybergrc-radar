const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ranking = require('../deal-ranking.js');

const day = '2026-11-18';
const nicheFree = (title, provider = 'Red Team Leaders', extra = {}) => ({
  title, provider, kind: 'Free exam', price: '$0 exam with NEXTSTEP100',
  verifiedOn: day, deadline: '2026-11-20', score: 99, ...extra
});
const giacDiscount = {
  title: 'GIAC certification exam voucher', provider: 'GIAC', kind: 'Discount',
  price: '20% off', source: 'https://www.giac.org/pricing', verifiedOn: '2026-11-01', score: 55
};

test('a recognized certification deal outranks a newer, expiring niche free exam', () => {
  const free = nicheFree('Certified GRC Professional');
  assert.ok(ranking.score(giacDiscount, day) > ranking.score(free, day));
  assert.ok(ranking.compare(giacDiscount, free, day) < 0);
});

test('recognition alone does not put a modest training sale above a direct exam deal', () => {
  const training = {
    title: 'SANS training course discount', provider: 'SANS', kind: 'Discount',
    price: '10% off', verifiedOn: day, score: 99
  };
  assert.ok(ranking.score(training, day) < ranking.score(nicheFree('Certified GRC Professional'), day));
});

test('the spotlight allows only one slot per issuer, including alternate spellings and brands', () => {
  const sans = {...giacDiscount, title: 'SANS and GIAC exam offer', provider: 'SANS Institute', price: '10% off'};
  const niche1 = nicheFree('Certified GRC Professional');
  const niche2 = nicheFree('Network Security Fundamentals', 'RedTeamLeaders');
  const different = nicheFree('Network Fundamentals', 'Another Provider', {price: 'Free'});
  const alternatives = [niche2, niche1, different, sans, giacDiscount];
  const picks = ranking.spotlight(alternatives, day);
  assert.deepEqual(picks, [giacDiscount, niche1, different]);
  assert.deepEqual(ranking.spotlight([niche1, niche2], day), [niche1]);
  assert.equal(alternatives.length, 5);
});

test('opportunity feed can diversify by issuer without changing score order', () => {
  const items = [
    {provider: 'RedTeamLeaders', rank: 66}, {provider: 'Red Team Leaders', rank: 65},
    {provider: 'Cloud Security Alliance', rank: 56}, {provider: 'OffSec', rank: 51}
  ];
  assert.deepEqual(ranking.diverse(items, 3, ranking.providerKey), [items[0], items[2], items[3]]);
});

test('the site excludes unavailable offers from spotlight without deleting catalog records', () => {
  const files = name => fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
  const html = files('index.html');
  const offers = [
    giacDiscount,
    nicheFree('Current GRC exam'),
    nicheFree('Expired exam', 'Provider A', {deadline: '2026-11-17'}),
    nicheFree('Upcoming exam', 'Provider B', {startDate: '2026-11-19'}),
    nicheFree('Flagged exam', 'Provider C', {id: 'flagged'}),
    nicheFree('Paused exam', 'Provider D', {publicationStatus: 'paused'}),
    nicheFree('Active exam', 'Provider E', {publicationStatus: 'active'})
  ];
  const helpers = ['offerState', 'expired', 'sourceHealth']
    .map(key => html.match(new RegExp('const '+key+'=[^;]+;'))[0]).join('');
  const healthGate = html.slice(html.indexOf('const isFlagged='), html.indexOf('const days='));
  const gate = html.slice(html.indexOf('function isCurrentOffer('), html.indexOf('function renderUnifiedFeed('));
  const picks = vm.runInNewContext(helpers + healthGate + gate +
     '; ranking.spotlight(offers.filter(isCurrentOffer), day)', {
        offers, revalidationData: {results:[{id:'flagged', status:'changed'}]}, ranking, day
      });
  assert.deepEqual(Array.from(picks, d => d.title), [giacDiscount.title, 'Current GRC exam', 'Active exam']);
  assert.equal(offers.length, 7);
});
