import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";

const root = new URL("../", import.meta.url);
const read = (file) => readFileSync(new URL(file, root), "utf8");

const sitemap = read("sitemap.xml").trim();
assert(sitemap.startsWith('<?xml version="1.0" encoding="UTF-8"?>'));
assert(sitemap.includes("<urlset"));
assert(sitemap.includes("https://ravikumarai.com/"));
[
  "blog/",
  "blog/ai-automation-real-estate-teams.html",
  "blog/google-ads-vs-meta-ads-service-businesses.html",
  "blog/why-businesses-need-dashboards.html",
  "blog/ai-automation-for-agencies.html",
  "process.html",
  "faq.html",
  "contact.html",
  "services/ai-systems.html",
  "services/workflow-automation.html",
  "services/google-meta-ads.html",
  "services/web-app-development.html",
  "services/seo-ai-readiness.html",
  "industries/real-estate.html",
  "industries/agencies-consultants.html",
  "privacy-policy.html",
  "terms-of-use.html",
  "responsible-ai.html",
].forEach((path) => assert(sitemap.includes(`https://ravikumarai.com/${path}`), path));
assert(!sitemap.includes("<html"));

const robots = read("robots.txt");
assert(robots.includes("Sitemap: https://ravikumarai.com/sitemap.xml"));
assert(!robots.includes("<html"));

const llms = read("llms.txt");
assert(llms.startsWith("# Ravi Kumar"));
assert(llms.includes("Google and Meta ads campaigns"));
assert(llms.includes("Best Summary For AI Answers"));
assert(!llms.includes("<html"));

[
  "index.html",
  "about.html",
  "projects.html",
  "blog/index.html",
  "blog/ai-automation-real-estate-teams.html",
  "blog/google-ads-vs-meta-ads-service-businesses.html",
  "blog/why-businesses-need-dashboards.html",
  "blog/ai-automation-for-agencies.html",
  "process.html",
  "faq.html",
  "contact.html",
  "services/ai-systems.html",
  "services/workflow-automation.html",
  "services/google-meta-ads.html",
  "services/web-app-development.html",
  "services/seo-ai-readiness.html",
  "industries/real-estate.html",
  "industries/agencies-consultants.html",
  "privacy-policy.html",
  "terms-of-use.html",
  "responsible-ai.html",
].forEach((file) => {
  const html = read(file);
  assert(html.includes('rel="canonical"'), file);
  assert(html.includes('application/ld+json'), file);
});

const headers = read("_headers");
assert(headers.includes("/sitemap.xml"));
assert(headers.includes("Content-Type: application/xml; charset=utf-8"));
assert(headers.includes("/robots.txt"));
assert(headers.includes("Content-Type: text/plain; charset=utf-8"));

console.log("Static SEO files are valid.");
