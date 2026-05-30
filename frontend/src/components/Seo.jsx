import { useEffect } from 'react';

/**
 * Per-route document metadata for the SPA.
 *
 * index.html ships a full set of SEO tags (title, description, canonical,
 * Open Graph, Twitter, JSON-LD) so social scrapers and crawlers that DON'T
 * execute JS still see correct metadata for the entry URL. This component
 * keeps those same tags correct as the user (or a JS-rendering crawler such
 * as Googlebot) navigates between routes.
 *
 * It mutates the existing head tags in place — never appends duplicates — so
 * there is always exactly one <title>, one canonical, and one of each meta.
 * That avoids the duplicate-canonical / conflicting-robots problems you'd get
 * from naively rendering metadata tags per route.
 *
 * Usage:
 *   <Seo path="/" description="…" />                 // indexed page
 *   <Seo title="Find your hospital" path="/portal" />
 *   <Seo noindex title="Secure workspace" />         // private / auth pages
 */

const SITE_NAME = 'MediFleet';
const ORIGIN = 'https://www.medifleet.app';
const DEFAULT_DESCRIPTION =
  'MediFleet is a multi-tenant hospital management platform unifying registration, clinical desk, pharmacy, lab, radiology, wards, and billing in one secure, audited workspace.';
const DEFAULT_OG_IMAGE = `${ORIGIN}/og-image.svg`;

function upsertMeta(attr, key, content) {
  if (content == null) return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}

function upsertLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!href) {
    // noindex routes shouldn't advertise a canonical URL
    if (el) el.remove();
    return;
  }
  if (!el) {
    el = document.createElement('link');
    el.setAttribute('rel', rel);
    document.head.appendChild(el);
  }
  el.setAttribute('href', href);
}

export default function Seo({
  title,
  description = DEFAULT_DESCRIPTION,
  // Absolute path of the current route, e.g. "/portal". Builds canonical +
  // og:url. Omit on noindex pages so no canonical is advertised.
  path,
  image = DEFAULT_OG_IMAGE,
  noindex = false,
}) {
  useEffect(() => {
    const fullTitle = title
      ? `${title} — ${SITE_NAME}`
      : `${SITE_NAME} — Multi-Hospital Management Platform`;
    const canonical = path ? `${ORIGIN}${path}` : null;
    const robots = noindex
      ? 'noindex, nofollow'
      : 'index, follow, max-image-preview:large, max-snippet:-1';

    document.title = fullTitle;
    upsertMeta('name', 'description', description);
    upsertMeta('name', 'robots', robots);
    upsertLink('canonical', canonical);

    // Open Graph
    upsertMeta('property', 'og:title', fullTitle);
    upsertMeta('property', 'og:description', description);
    upsertMeta('property', 'og:url', canonical || `${ORIGIN}/`);
    upsertMeta('property', 'og:image', image);

    // Twitter / X
    upsertMeta('name', 'twitter:title', fullTitle);
    upsertMeta('name', 'twitter:description', description);
    upsertMeta('name', 'twitter:image', image);
  }, [title, description, path, image, noindex]);

  return null;
}
