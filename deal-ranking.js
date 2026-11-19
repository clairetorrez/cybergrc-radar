/* Editorial ordering for the Radar catalog, not a measure of hiring outcomes. */
const radarDealRanking = (() => {
  const DAY_MS = 86400000;
  const issuers = [
    // Group alternate brand names and official hosts before allocating spotlight slots.
    ['sans-giac', 34, ['sans', 'sansinstitute', 'giac', 'giaccertifications', 'sansgiac'], ['sans.org', 'giac.org']],
    ['isc2', 34, ['isc2', 'isc'], ['isc2.org']],
    ['isaca', 34, ['isaca'], ['isaca.org']],
    ['aws', 34, ['aws', 'amazonwebservices'], ['aws.amazon.com']],
    ['microsoft', 34, ['microsoft', 'microsoftlearn'], ['learn.microsoft.com']],
    ['google-cloud', 34, ['googlecloud', 'googlecloudskillsboost'], ['cloud.google.com', 'cloudskillsboost.google']],
    ['comptia', 34, ['comptia'], ['comptia.org']],
    ['cisco', 34, ['cisco'], ['cisco.com']],
    ['linux-foundation', 34, ['linuxfoundation', 'thelinuxfoundation', 'cncf', 'cloudnativecomputingfoundation'], ['linuxfoundation.org', 'cncf.io']],
    ['offsec', 34, ['offsec', 'offensivesecurity'], ['offsec.com']],
    ['pecb', 26, ['pecb'], ['pecb.com']],
    ['iapp', 32, ['iapp', 'internationalassociationofprivacyprofessionals'], ['iapp.org']],
    ['csa', 26, ['csa', 'cloudsecurityalliance'], ['cloudsecurityalliance.org']],
    ['isa', 26, ['isa', 'internationalsocietyofautomation'], ['isa.org']],
  ];

  const text = value => String(value || '').toLowerCase();
  const nameKey = value => text(value).replace(/[^a-z0-9]+/g, '');
  const time = date => /^\d{4}-\d{2}-\d{2}$/.test(date || '') ? Date.parse(date + 'T00:00:00Z') : NaN;

  function issuer(deal) {
    const name = nameKey(deal.provider);
    let host = '';
    try { host = new URL(deal.source || deal.url).hostname.replace(/^www\./, ''); } catch {}
    const known = issuers.find(([, , names, hosts]) =>
      names.includes(name) || hosts.some(domain => host === domain || host.endsWith('.' + domain)));
    return {key: known?.[0] || name || host, recognition: known?.[1] || 0};
  }

  function format(deal) {
    const kind = text(deal.kind);
    const terms = text([deal.title, deal.seasonalCategory, deal.price].join(' '));
    if (kind === 'free credential') return 32;
    if (/^free (?:exam|certification)$/.test(kind)) return 42;
    if (kind === 'certification benefit') return 32;
    if (!/discount/.test(kind)) return 0;
    if (/certifications?\b|\bexams?\b|exam tokens?|exam vouchers?/.test(terms)) return 42;
    if (/training|courses?|standards?|bootcamps?|labs?/.test(terms)) return 24;
    return 18;
  }

  function savings(deal) {
    const price = text([deal.price, deal.discount].join(' '));
    if (/^free (?:exam|certification|credential)$/i.test(deal.kind)) return 12;
    // Use stated savings, never a list price. Cap the effect of large or "up to" promotions.
    const offers = [...price.matchAll(/(?:\b(up to)\s+)?(\d{1,3})\s*%\s*off\b/g)]
      .map(([, upTo, percent]) => Math.min(12, Number(percent) * 0.17) * (upTo ? 0.5 : 1));
    const cash = [...price.matchAll(/(?:\b(up to)\s+)?\$([\d,]+(?:\.\d{1,2})?)\s*off\b/g)]
      .map(([, upTo, dollars]) => Math.min(12, Math.log10(1 + Number(dollars.replace(/,/g, ''))) * 4) * (upTo ? 0.5 : 1));
    return Math.max(0, ...offers, ...cash);
  }

  function score(deal, day) {
    const formatValue = format(deal);
    if (!formatValue) return 0;
    const relevance = /\b(grc|governance|compliance|it audit|risk management)\b/.test(
      text([deal.title, deal.category, ...(deal.frameworks || [])].join(' '))) ? 5 : 0;
    const age = (time(day) - time(deal.verifiedOn)) / DAY_MS;
    const daysLeft = (time(deal.deadline) - time(day)) / DAY_MS;
    const freshness = Number.isFinite(age) ? Math.max(0, 4 - Math.max(0, age) / 7) : 0;
    const urgency = daysLeft >= 0 && daysLeft <= 14 ? (daysLeft <= 7 ? 5 : 3) : 0;
    return formatValue + issuer(deal).recognition + relevance + savings(deal) + freshness + urgency;
  }

  function compare(a, b, day) {
    return score(b, day) - score(a, day)
      || (Number(b.score) || 0) - (Number(a.score) || 0)
      || String(a.title || '').localeCompare(String(b.title || ''));
  }

  function diverse(items, limit, key) {
    const seen = new Set();
    const picks = [];
    for (const item of items) {
      if (picks.length >= limit) break;
      const group = key(item);
      if (group && seen.has(group)) continue;
      if (group) seen.add(group);
      picks.push(item);
    }
    return picks;
  }

  // The caller supplies current verified deals after applying catalog health and availability.
  function spotlight(offers, day, limit = 3) {
    const ranked = offers.filter(d => format(d) && text(d.kind) !== 'certification benefit')
      .sort((a, b) => compare(a, b, day));
    return diverse(ranked, limit, d => issuer(d).key);
  }

  return {score, compare, spotlight, diverse, providerKey: d => issuer(d).key};
})();

if (typeof module !== 'undefined' && module.exports) module.exports = radarDealRanking;
