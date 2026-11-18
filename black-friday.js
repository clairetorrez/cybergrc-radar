const blackFriday2026 = (() => {
  const label = 'Black Friday';
  const opens = '2026-11-18';
  const cyberMonday = '2026-11-30';
  const lastDay = '2027-01-04';
  const source = 'https://github.com/v3nomtech/infosec-cert-black-friday-2026';
  function urlKey(value) {
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password) return '';
      return url.hostname.replace(/^www\./, '') + url.pathname.replace(/\/$/, '');
    } catch { return ''; }
  }
  function status(offer, day, now = Date.now()) {
    if (offer.closedBySource || (offer.endAt ? now >= Date.parse(offer.endAt) : (offer.deadline || cyberMonday) < day)) return 'closed';
    if (offer.startAt ? now < Date.parse(offer.startAt) : offer.startDate && offer.startDate > day) return 'upcoming';
    return 'live';
  }
  function merge(base, entries) {
    const result = [...base];
    const indexes = new Map(result.map((d, i) => [urlKey(d.source), i]));
    for (const entry of entries) {
      if (entry.verification !== 'vendor' || !urlKey(entry.source) || !urlKey(entry.evidence)) continue;
      const i = indexes.get(urlKey(entry.source));
      const existing = result[i];
      const deal = {
        ...existing,
        ...entry,
        id: existing?.id || entry.id,
        title: existing?.title || entry.title,
        category: existing?.category || 'Security training',
        seasonalCategory: entry.category,
        kind: 'Discount',
        blackFriday: true,
        description: existing?.description || entry.title,
        eligibility: [existing?.eligibility || entry.details || 'See the provider for eligibility and terms.',
          !entry.deadline ? 'The provider has not published an end date.' : 'Scheduled through ' + entry.deadline + '.'].join(' '),
        frameworks: [...new Set([...(existing?.frameworks || []), ...entry.frameworks])],
        score: existing?.score || 75
      };
      if (i === undefined) {
        indexes.set(urlKey(deal.source), result.length);
        result.push(deal);
      } else result[i] = deal;
    }
    return result.map(d => !d.blackFriday && d.kind === 'Discount' &&
      (d.startDate || d.deadline || '').startsWith('2026-') && /black friday|cyber monday/i.test(d.title)
      ? {...d, blackFriday: true} : d);
  }
  return {label, opens, cyberMonday, lastDay, source, urlKey, status, merge};
})();
