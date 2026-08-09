import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { strict as assert } from "node:assert";

const root = new URL("../", import.meta.url).pathname;
const read = (file) => readFileSync(join(root, file), "utf8");
const bytes = (file) => statSync(join(root, file)).size;

const index = read("index.html");
const projects = read("projects.html");
const about = read("about.html");
const headers = read("_headers");
const bottomLinks = read("assets/bottom-links.css");
const seoPage = read("assets/seo-page.css");

const introMatch = index.match(/<img[^>]+loading="eager"[^>]+src="assets\/images\/mobile-character-intro-368\.webp"[^>]*>/);
assert(introMatch, "mobile intro LCP image must be present in initial HTML");
const introImg = introMatch[0];
assert(introImg.includes('loading="eager"'), "mobile intro LCP image must not be lazy-loaded");
assert(introImg.includes('fetchpriority="high"'), "mobile intro LCP image must use high fetch priority");
assert(introImg.includes('width="368"') && introImg.includes('height="560"'), "mobile intro image needs explicit dimensions");

for (const file of ["mobile-character-services-368.webp", "mobile-character-portfolio-373.webp"]) {
  const re = new RegExp(`<img[^>]+src="assets/images/${file}"[^>]*>`);
  const match = index.match(re);
  assert(match, `${file} must be present`);
  assert(match[0].includes('loading="lazy"'), `${file} should remain lazy-loaded`);
  assert(match[0].includes("width=") && match[0].includes("height="), `${file} needs explicit dimensions`);
}

for (const html of [index, projects]) {
  assert(!/<iframe\b[^>]*\ssrc=/i.test(html), "project iframe previews must not have eager src attributes");
  assert(/<iframe\b[^>]*\sdata-src=/i.test(html), "project iframe previews should retain data-src for interaction loading");
}

for (const file of ["index.html", "about.html", "projects.html"]) {
  const html = read(file);
  assert.equal((html.match(/rel="preconnect" href="https:\/\/fonts\.googleapis\.com"/g) || []).length, 1, `${file} should have one fonts.googleapis preconnect`);
  assert.equal((html.match(/rel="preconnect" href="https:\/\/fonts\.gstatic\.com"/g) || []).length, 1, `${file} should have one fonts.gstatic preconnect`);
}

assert(!/rel="preconnect"[^>]+babybabarj\.github\.io/i.test(index), "GitHub Pages should not be preconnected on initial homepage load");
assert(!/rel="dns-prefetch"[^>]+babybabarj\.github\.io/i.test(index), "GitHub Pages should not be dns-prefetched on initial homepage load");

for (const file of [
  "assets/images/mobile-character-intro.webp",
  "assets/images/mobile-character-intro-368.webp",
  "assets/images/mobile-character-services.webp",
  "assets/images/mobile-character-portfolio.webp",
]) {
  assert(bytes(file) < 200_000, `${file} exceeds the mobile character budget`);
}

for (const file of [
  "assets/images/project-whatsroute-home-960.webp",
  "assets/images/project-dimpleit-home-960.webp",
  "assets/images/project-aurelia-home-960.webp",
  "assets/images/project-arion-home-960.webp",
]) {
  assert(bytes(file) < 120_000, `${file} exceeds the project screenshot budget`);
}

assert(bytes("assets/images/ravi-kumar-logo-320.webp") < 25_000, "responsive logo exceeds logo budget");

assert(headers.includes("Strict-Transport-Security: max-age=31536000"), "HSTS header missing");
assert(headers.includes("Content-Security-Policy-Report-Only:"), "CSP Report-Only header missing");
assert(!/\/assets\/\*\s+Cache-Control:[^\n]+immutable/s.test(headers), "non-fingerprinted assets must not be immutable");

const greenSources = [index, projects, about, bottomLinks, seoPage].join("\n");
assert(!/#25d366/i.test(greenSources), "WhatsApp green should use the darker accessible brand green");
assert(greenSources.includes("#128c7e"), "accessible WhatsApp green is missing");

const projectLabels = [
  "Open WhatsRoute project in a new tab",
  "Open Dimpleit project in a new tab",
  "Open Aurelia Villas Dubai project in a new tab",
  "Open ARION Energy Drink project in a new tab",
];
for (const label of projectLabels) {
  assert(index.includes(`aria-label="${label}"`), `index missing ${label}`);
  assert(projects.includes(`aria-label="${label}"`), `projects missing ${label}`);
}

console.log("Performance and accessibility regressions are covered.");
