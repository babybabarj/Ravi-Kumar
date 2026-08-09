# RaviKumarAI.com Performance Budget

This budget protects the current visual experience while keeping mobile load fast enough for search, AI crawlers, and real users on slower networks.

## Initial Page Budget

- Mobile LCP image: preferred under 150 KB, hard ceiling 200 KB.
- Initial local image transfer: preferred under 1 MB.
- Initial page transfer: preferred under 1.5-2 MB.
- Third-party project runtimes before interaction: 0.
- Critical JavaScript: keep under 100 KB compressed where practical.
- Font origins: at most Google Fonts CSS and Google Fonts static font origin unless fonts are self-hosted.

## Asset Budget

- Mobile character images: each under 200 KB at the largest mobile-served size.
- Project screenshots: largest commonly served version under 120 KB.
- Logo raster fallback: preferred under 25 KB for the rendered size.
- Non-fingerprinted assets: do not use immutable caching.

## Required Regression Checks

- The mobile intro character must be discoverable in the initial HTML, eager or default-loaded, and marked `fetchpriority="high"`.
- Below-fold character images and project screenshots remain lazy-loaded.
- Project iframe previews use `data-src` until explicit interaction.
- Project open links have unique accessible names.
- `robots.txt`, `sitemap.xml`, `llms.txt`, canonical tags, and structured data must remain valid.
