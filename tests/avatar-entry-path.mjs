import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const sectionPoint = html.match(/function sectionPoint\(raw\)\{[\s\S]*?\n  \}/)?.[0] || '';

assert.match(sectionPoint, /b\.id === 'projects' \? projectAvatarPoint\(b\) : null/);
assert.match(sectionPoint, /const bx = projectEntry \? projectEntry\.x/);
assert.match(sectionPoint, /const by = projectEntry \? projectEntry\.y/);
