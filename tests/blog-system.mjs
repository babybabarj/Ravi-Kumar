import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, normalize } from "node:path";
import { strict as assert } from "node:assert";

const root = new URL("../", import.meta.url).pathname;
const read = (file) => readFileSync(join(root, file), "utf8");
const exists = (file) => existsSync(join(root, file));

const retained = [
  "blog/ai-automation-real-estate-teams.html",
  "blog/google-ads-vs-meta-ads-service-businesses.html",
  "blog/why-businesses-need-dashboards.html",
  "blog/ai-automation-for-agencies.html",
];
const retiredGithubPagesHost = ["babybabarj.github.io", "Ravi-Kumar"].join("/");

const redirects = new Map(
  read("_redirects")
    .split(/\r?\n/)
    .map((line) => line.trim().split(/\s+/))
    .filter((parts) => parts.length >= 3 && parts[2] === "301")
    .map(([from, to]) => [from, to]),
);

const redirectSources = [
  "/blogs.html",
  "/blog/ai-automation-real-estate.html",
  "/blog/google-meta-ads-service-businesses.html",
  "/blog/dashboards-before-ai.html",
];

assert(!exists("CNAME"), "CNAME must not exist");
assert(!read(".ravikumarai-blog/config.json").includes('"autopublish_enabled": true'));
assert(read(".ravikumarai-blog/config.json").includes('"approval_required": true'));
assert(read(".ravikumarai-blog/config.json").includes('"push": false'));

assert.equal(redirects.get("/blogs.html"), "/blog/");
for (const source of redirectSources.slice(1)) assert(redirects.has(source), source);

const blogIndex = read("blog/index.html");
assert(blogIndex.includes('rel="canonical" href="https://ravikumarai.com/blog/"'));
assert(!blogIndex.includes("blogs.html"));
for (const file of retained) assert(blogIndex.includes(file.replace("blog/", "")), file);

const sitemap = read("sitemap.xml");
const feed = read("blog/feed.xml");
for (const file of retained) {
  const url = `https://ravikumarai.com/${file}`;
  assert(sitemap.includes(url), `sitemap missing ${url}`);
  assert(feed.includes(url), `feed missing ${url}`);
}
for (const source of redirectSources) {
  assert(!sitemap.includes(`https://ravikumarai.com${source}`), `redirect in sitemap ${source}`);
}

for (const file of retained) {
  const html = read(file);
  assert(hasBlogLink(html), `${file} missing active Blog nav`);
  assert(html.includes('"@type":"BlogPosting"') || html.includes('"@type": "BlogPosting"'), `${file} missing BlogPosting`);
  assert(html.includes("Ravi Kumar"), `${file} missing author/name`);
  assert(html.includes("Sources and review"), `${file} missing sources section`);
}

const publicFiles = readdirSync(root, { recursive: true })
  .map(String)
  .filter((file) => file.endsWith(".html") || file.endsWith(".xml") || file.endsWith(".txt"))
  .filter((file) => !file.startsWith("node_modules/") && !file.startsWith(".git/"));

for (const file of publicFiles) {
  assert(!read(file).includes(retiredGithubPagesHost), `${file} has old GitHub Pages URL`);
}

const htmlFiles = publicFiles.filter((file) => file.endsWith(".html"));
for (const file of htmlFiles) {
  const html = read(file);
  if (html.includes("navLinks")) assert(hasBlogLink(html), `${file} desktop nav missing Blog`);
  if (html.includes("mobileMenuLinks")) assert(html.includes('href="/blog/">Blog</a>'), `${file} mobile nav missing Blog`);

  for (const [, raw] of html.matchAll(/\b(?:href|src)=["']([^"']+)["']/g)) {
    if (/^(?:https?:|mailto:|tel:|sms:|data:|javascript:|#)/i.test(raw)) {
      if (raw.startsWith("https://ravikumarai.com/")) {
        const path = new URL(raw).pathname;
        assert(resolveLocal(path) || redirects.has(path), `${file} broken canonical link ${raw}`);
      }
      continue;
    }
    const clean = raw.split(/[?#]/)[0];
    if (!clean || clean.startsWith("#")) continue;
    const base = file.includes("/") ? file.split("/").slice(0, -1).join("/") : "";
    const path = clean.startsWith("/") ? clean : normalize(join("/", base, clean));
    assert(resolveLocal(path) || redirects.has(path), `${file} broken local link ${raw}`);
  }
}

function hasBlogLink(html) {
  return html.includes('href="/blog/">Blog</a>') ||
    html.includes('href="/blog/" class="active">Blog</a>') ||
    html.includes('class="active" href="/blog/">Blog</a>');
}

function resolveLocal(path) {
  if (path === "/") return exists("index.html");
  const clean = path.replace(/^\/+/, "");
  if (clean.endsWith("/")) return exists(`${clean}index.html`);
  return exists(clean) || exists(`${clean}.html`) || exists(`${clean}/index.html`);
}

console.log("Blog consolidation checks are valid.");
